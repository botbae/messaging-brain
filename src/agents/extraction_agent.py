"""ExtractionAgent — converts a ClientBrief into structured positioning decisions.

Called by WritingAgent.extract_positioning_decisions() when no brain_decisions
are preloaded. Can also be called directly from the API or pipeline.

Uses agents/prompts/extraction.md as the system prompt.
All LLM calls go through core.model_provider.generate (never core.llm directly).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

from core.model_provider import generate as llm_generate
from core.utils import clean_phrase, clean_sentence


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DECISION_KEYS: tuple[str, ...] = (
    "icp",
    "primary_problem",
    "current_alternative",
    "desired_outcome",
    "category_frame",
    "differentiation",
    "anti_positioning",
)

_BANNED_WORDS: tuple[str, ...] = (
    "streamline", "empower", "unlock", "innovative", "cutting-edge",
    "revolutionize", "best-in-class",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_prompt(filename: str) -> str:
    path = Path(__file__).parent / "prompts" / filename
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


def _contains_banned(text: str) -> bool:
    lower = (text or "").lower()
    return any(b in lower for b in _BANNED_WORDS)


def _jaccard(a: str, b: str) -> float:
    """Token-level Jaccard overlap between two strings."""
    ta = set(re.sub(r"[^\w\s]", "", (a or "").lower()).split())
    tb = set(re.sub(r"[^\w\s]", "", (b or "").lower()).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _ground_decisions(decisions: dict, brief) -> tuple[dict, list[str]]:
    """Patch decision fields that have drifted from brief fields.

    Mirrors GroundingAgent.ground() without importing from writing_agent
    (avoiding circular import). Threshold: minimum 0.05 Jaccard overlap.
    """
    THRESHOLD = 0.05
    patched = dict(decisions)
    notes: list[str] = []

    icp = patched.get("icp", "")
    if _jaccard(icp, brief.audience or "") < THRESHOLD:
        patched["icp"] = clean_phrase(brief.audience) or icp
        notes.append("icp: low overlap with brief.audience — patched")

    problem = patched.get("primary_problem", "")
    if _jaccard(problem, brief.pain or "") < THRESHOLD:
        patched["primary_problem"] = clean_sentence(brief.pain or problem)
        notes.append("primary_problem: low overlap with brief.pain — patched")

    return patched, notes


# ---------------------------------------------------------------------------
# ExtractionAgent
# ---------------------------------------------------------------------------

class ExtractionAgent:
    """Extracts structured positioning decisions from a ClientBrief via LLM.

    Pattern:
        agent = ExtractionAgent()
        decisions = agent.run(brief)   # returns dict with all 7 decision keys

    Falls back to brief-derived values when both LLM passes fail.
    """

    def __init__(self) -> None:
        self._prompt = _load_prompt("extraction.md")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, brief) -> dict:
        """Return a positioning decisions dict for the given brief.

        Tries two LLM passes (normal then strict). Falls back to
        brief-derived values if both fail or return invalid JSON.

        Args:
            brief: ClientBrief (or any object with .product, .audience,
                   .pain, .offer, .tone, .examples, .context attributes)

        Returns:
            dict with keys: icp, primary_problem, current_alternative,
            desired_outcome, category_frame, differentiation, anti_positioning
        """
        system = self._prompt or self._default_system()
        user = self._build_user(brief)

        # Pass 1: normal temperature
        result = self._try_generate(system, user, temperature=0.2)

        # Pass 2: strict prompt at lower temperature
        if result is None:
            system_strict = (
                "You are a product positioning strategist. Output ONLY valid JSON. "
                "No markdown, no code fences, no explanation, no extra keys. "
                "Exactly 7 keys: icp, primary_problem, current_alternative, desired_outcome, "
                "category_frame, differentiation, anti_positioning. "
                "Each value: one short concrete sentence. "
                "Banned words: streamline, empower, unlock, innovative, cutting-edge, "
                "revolutionize, best-in-class."
            )
            result = self._try_generate(system_strict, user, temperature=0.15)

        if result is not None:
            result, _ = _ground_decisions(result, brief)
            if os.getenv("DEBUG_DECISIONS", "").lower() == "true":
                self._print_decisions(result)
            return result

        fallback = self._fallback(brief)
        if os.getenv("DEBUG_DECISIONS", "").lower() == "true":
            self._print_decisions(fallback)
        return fallback

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_user(self, brief) -> str:
        tone = (brief.tone or "Clear and direct").strip()
        parts = [
            "Extract positioning decisions from this brief.",
            f"product: {brief.product or 'Not specified'}",
            f"audience: {brief.audience or 'Not specified'}",
            f"pain: {brief.pain or 'Not specified'}",
            f"offer: {brief.offer or 'Not specified'}",
            f"User custom instructions (tone): {tone}",
        ]
        if getattr(brief, "examples", None):
            parts.append(f"examples: {brief.examples}")
        if getattr(brief, "context", None):
            parts.append(f"context: {brief.context}")
        parts.append(
            "Return valid JSON with EXACTLY these keys (each value a short, concrete sentence): "
            "icp, primary_problem, current_alternative, desired_outcome, category_frame, "
            "differentiation, anti_positioning. "
            "Do NOT use vague words: streamline, empower, unlock, innovative, cutting-edge, "
            "revolutionize, best-in-class."
        )
        return "\n".join(parts)

    def _try_generate(self, system: str, user: str, temperature: float) -> Optional[dict]:
        try:
            raw = llm_generate(
                system=system,
                user=user,
                model="llama3:8b",
                temperature=temperature,
                agent_name="extraction",
            )
            return self._parse(raw)
        except Exception:
            return None

    def _parse(self, raw: str) -> Optional[dict]:
        """Parse and validate JSON from LLM output. Returns None on any failure."""
        if not raw or not raw.strip():
            return None
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            start = next((i for i, l in enumerate(lines) if "{" in l), 0)
            end = next((i for i in range(len(lines) - 1, -1, -1) if "}" in lines[i]), len(lines))
            text = "\n".join(lines[start : end + 1])
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        for k in _DECISION_KEYS:
            if k not in data or not isinstance(data.get(k), str):
                return None
        result = {k: (data[k] or "").strip() for k in _DECISION_KEYS}
        if not all(result[k] for k in _DECISION_KEYS):
            return None
        if _contains_banned(" ".join(result.values())):
            return None
        return result

    def _fallback(self, brief) -> dict:
        """Brief-derived fallback when LLM is unavailable or returns invalid output."""
        product = clean_phrase(brief.product) or "Product"
        audience = clean_phrase(brief.audience) or "Target audience"
        pain = clean_sentence(brief.pain or "Core problem not yet articulated.")
        offer = clean_phrase(brief.offer) or "A clearer, faster path to the outcome they need"
        audience_lower = audience.lower().rstrip(".")
        offer_lower = offer.lower().rstrip(".")
        return {
            "icp": audience,
            "primary_problem": pain,
            "current_alternative": (
                f"Existing tools and manual approaches that {audience_lower} use today "
                f"but were not built specifically for {offer_lower}."
            ),
            "desired_outcome": (
                clean_sentence(offer) if offer
                else f"{product} helps {audience_lower} reach the outcome they care about."
            ),
            "category_frame": f"{product} for {audience_lower}.",
            "differentiation": (
                f"Built specifically for {audience_lower} — not a general-purpose tool "
                f"repurposed for this problem. Focused entirely on {offer_lower}."
            ),
            "anti_positioning": (
                f"Not a broad platform trying to do everything. "
                f"Designed around the specific problem {audience_lower} face, "
                f"not the category they sit in."
            ),
        }

    def _default_system(self) -> str:
        return (
            "You are a product positioning strategist. "
            "Make concrete strategic decisions. No marketing tone. No storytelling. No hype language. "
            "Output must be STRICT JSON only. No markdown. No explanation text. "
            "No extra keys. No headings."
        )

    def _print_decisions(self, decisions: dict) -> None:  # pragma: no cover
        ordered = (
            ("ICP", "icp"),
            ("Primary Problem", "primary_problem"),
            ("Current Alternative", "current_alternative"),
            ("Desired Outcome", "desired_outcome"),
            ("Category Frame", "category_frame"),
            ("Differentiation", "differentiation"),
            ("Anti-Positioning", "anti_positioning"),
        )
        print("— POSITIONING DECISIONS (ExtractionAgent) —")
        for label, key in ordered:
            print(f"{label}: {decisions.get(key, '')}")
