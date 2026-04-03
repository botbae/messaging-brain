"""StructuringAgent — generates a dynamic landing page IA from a ProductProfile.

Input:  ProductProfile + optional ConfidenceReport
Output: dict matching the IA schema:
    {
      "sections": [{"type", "title", "purpose", "copy": {headline, subhead, cta, bullets}, "notes"}],
      "meta": {"tone", "words_to_avoid", "optional_sections"}
    }

The agent decides section types and order based on product type, audience, and problem.
It does NOT write final copy — that is WritingAgent's job.

Uses agents/prompts/structuring.md as the system prompt.
All LLM calls go through core.model_provider.generate.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from core.model_provider import generate as llm_generate

if TYPE_CHECKING:
    from schemas.confidence_report import ConfidenceReport
    from product_profile import ProductProfile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_SECTION_TYPES = frozenset({
    "hero", "problem", "why_fail", "product", "how_it_works", "proof", "cta", "other",
})

_EMPTY_FALLBACK: dict = {
    "sections": [],
    "meta": {
        "tone": "",
        "words_to_avoid": [],
        "optional_sections": [],
    },
}

_LLM_TIMEOUT = 15  # seconds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_prompt(filename: str) -> str:
    path = Path(__file__).parent / "prompts" / filename
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


# ---------------------------------------------------------------------------
# StructuringAgent
# ---------------------------------------------------------------------------

class StructuringAgent:
    """Generates a dynamic landing page IA dict from a ProductProfile.

    Pattern:
        agent = StructuringAgent()
        ia_dict = agent.run(profile)
        ia_dict = agent.run(profile, confidence_report=report)

    Falls back to a minimal hero + cta dict when the LLM fails or returns invalid JSON.
    """

    def __init__(self) -> None:
        self._prompt = _load_prompt("structuring.md")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        profile: "ProductProfile",
        confidence_report: Optional["ConfidenceReport"] = None,
    ) -> dict:
        """Generate a landing page IA dict for the given profile.

        Attempts the LLM call up to 2 times (1 retry) with a 15-second timeout each.
        On timeout the executor is shut down non-blocking so the caller is never held.
        Returns _EMPTY_FALLBACK after two failed attempts (timeout, error, or parse).
        Always returns a valid dict — never raises.
        """
        system = self._prompt or self._default_system()
        user = self._build_user(profile, confidence_report)
        product = getattr(profile, "product", "unknown")

        for attempt in range(2):
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            try:
                future = executor.submit(
                    llm_generate,
                    system=system,
                    user=user,
                    model="llama3:8b",
                    temperature=0.3,
                    agent_name="structuring",
                )
                raw = future.result(timeout=_LLM_TIMEOUT)
            except TimeoutError:
                logger.warning(
                    "structuring_agent: LLM timed out after %ds (attempt %d) for %s",
                    _LLM_TIMEOUT, attempt + 1, product,
                )
                future.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
                if attempt == 0:
                    continue
                return _EMPTY_FALLBACK
            except Exception as e:
                logger.error(
                    "structuring_agent: LLM call failed (attempt %d) for %s — %s",
                    attempt + 1, product, e,
                )
                executor.shutdown(wait=False)
                if attempt == 0:
                    continue
                return _EMPTY_FALLBACK
            else:
                executor.shutdown(wait=False)

            ia = self._parse(raw)
            if ia is not None:
                return ia
            logger.warning(
                "structuring_agent: parse failed on attempt %d for %s",
                attempt + 1, product,
            )

        logger.warning(
            "structuring_agent: returning empty fallback after 2 attempts for %s", product,
        )
        return _EMPTY_FALLBACK

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_user(
        self,
        profile: "ProductProfile",
        confidence_report: Optional["ConfidenceReport"],
    ) -> str:
        decisions = profile.decisions or {}
        parts = [
            f"Product: {profile.product or 'Unknown'}",
            f"Audience (ICP): {profile.audience or decisions.get('icp', 'Not specified')}",
            f"Core Problem: {profile.problem or decisions.get('primary_problem', 'Not specified')}",
            f"Current Alternatives: {decisions.get('current_alternative', 'Not specified')}",
            f"Differentiation: {profile.advantage or decisions.get('differentiation', 'Not specified')}",
            f"Category Frame: {decisions.get('category_frame', 'Not specified')}",
            f"Desired Outcome: {decisions.get('desired_outcome', profile.goal or 'Not specified')}",
            f"Tone: {profile.tone or 'Direct and specific'}",
        ]

        if confidence_report is not None:
            weak = [
                f.field_name for f in confidence_report.field_scores
                if f.status in ("weak", "missing")
            ]
            if weak:
                parts.append(
                    f"Note — weak or missing brain fields: {', '.join(weak)}. "
                    "Keep sections that depend on these fields shorter or mark as optional."
                )

        parts += [
            "",
            "Design a landing page IA for this product. Choose sections and order based on product type and audience.",
            "Output ONLY valid JSON matching the schema in your instructions. No markdown, no explanation.",
        ]
        return "\n".join(parts)

    def _parse(self, raw: str) -> Optional[dict]:
        """Parse LLM JSON output into a validated IA dict. Returns None on failure."""
        text = (raw or "").strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text)
            text = re.sub(r"\n?```\s*$", "", text.strip())
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            return None

        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError as e:
            logger.warning("structuring_agent: JSON parse error — %s", e)
            return None

        sections_raw = data.get("sections")
        if not isinstance(sections_raw, list) or not sections_raw:
            return None

        sections = []
        for s in sections_raw:
            if not isinstance(s, dict):
                continue
            section_type = s.get("type", "other")
            if section_type not in _VALID_SECTION_TYPES:
                section_type = "other"
            copy_raw = s.get("copy") or {}
            sections.append({
                "type": section_type,
                "title": str(s.get("title") or section_type.replace("_", " ").title()),
                "purpose": str(s.get("purpose") or ""),
                "copy": {
                    "headline": str(copy_raw.get("headline") or ""),
                    "subhead": str(copy_raw.get("subhead") or ""),
                    "cta": str(copy_raw.get("cta") or ""),
                    "bullets": [str(b) for b in copy_raw.get("bullets") or []],
                },
                "notes": [str(n) for n in (s.get("notes") or [])],
            })

        if not sections:
            return None

        meta_raw = data.get("meta") or {}
        return {
            "sections": sections,
            "meta": {
                "tone": str(meta_raw.get("tone") or ""),
                "words_to_avoid": [str(w) for w in (meta_raw.get("words_to_avoid") or [])],
                "optional_sections": [str(s) for s in (meta_raw.get("optional_sections") or [])],
            },
        }

    def _default_ia(self, profile: "ProductProfile") -> dict:
        """Minimal fallback IA when LLM fails — hero + cta only."""
        product = profile.product or "Product"
        audience = profile.audience or (profile.decisions or {}).get("icp") or "your audience"
        tone = profile.tone or "Direct and specific"

        return {
            "sections": [
                {
                    "type": "hero",
                    "title": "Hero",
                    "purpose": "Hook the visitor; state what this is and who it is for",
                    "copy": {
                        "headline": f"{product} — built for {audience}",
                        "subhead": profile.advantage or "",
                        "cta": "",
                        "bullets": [],
                    },
                    "notes": ["Lead with the outcome, not the mechanism. Keep headline under 8 words."],
                },
                {
                    "type": "cta",
                    "title": "Primary Call to Action",
                    "purpose": "Drive a single clear conversion action",
                    "copy": {
                        "headline": "Ready to get started?",
                        "subhead": "",
                        "cta": "Get started",
                        "bullets": [],
                    },
                    "notes": ["CTA label: 2-5 words, action verb, outcome-oriented."],
                },
            ],
            "meta": {
                "tone": tone,
                "words_to_avoid": [],
                "optional_sections": ["problem", "product", "how_it_works", "proof"],
            },
        }

    def _default_system(self) -> str:
        return (
            "You are a landing page architect. "
            "Given a product profile, design a dynamic landing page information architecture. "
            "Output ONLY valid JSON with keys: sections (array) and meta (object). "
            "Each section has: type, title, purpose, copy (headline/subhead/cta/bullets), notes."
        )
