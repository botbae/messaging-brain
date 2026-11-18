"""Positioning writer: validators, scoring and PositioningWriterMixin.

Split out of agents/writing_agent.py; import from there for a stable API.
"""

from typing import List, Optional

from core.model_provider import generate as llm_generate
from core.utils import clean_phrase, clean_sentence, lower_first
from agents.writing.common import (
    ClientBrief,
    _contains_banned_phrases,
    _print_decisions_if_debug,
    _run_with_retry,
    _section_first_line,
    _validate_headers,
)


_POSITIONING_HEADERS = (
    "PRODUCT",
    "ICP",
    "CORE PROBLEM",
    "CURRENT ALTERNATIVE",
    "WHY CURRENT OPTIONS FAIL",
    "DESIRED OUTCOME",
    "CATEGORY FRAME",
    "DIFFERENTIATION",
    "ANTI-POSITIONING",
    "POSITIONING STATEMENT",
    "MESSAGING NOTES",
)


_POSITIONING_BANNED = (
    "streamline", "empower", "unlock", "innovative", "cutting-edge", "revolutionize",
    "best-in-class", "game-changing", "stunning", "incredible", "amazing",
    "powerful solution", "modern platform", "seamless experience", "next generation",
    "all-in-one", "innovative platform", "end-to-end", "game changer",
    "disrupt", "disrupting", "ecosystem", "synergy", "leverage",
)


def _normalize_positioning_output(raw: str) -> str:
    """Strip preamble before PRODUCT header; remove markdown bold/heading markers; ensure headers on own line."""
    if not raw or not raw.strip():
        return raw or ""
    t = raw.strip()
    for start_header in ("PRODUCT", "**PRODUCT**", "## PRODUCT", "# PRODUCT"):
        idx = t.find(start_header)
        if idx > 0:
            t = t[idx:]
            break
    for h in _POSITIONING_HEADERS:
        t = t.replace(f"**{h}**", h)
        t = t.replace(f"**{h}", h)
        t = t.replace(f"{h}**", h)
        t = t.replace(f"## {h}", h)
        t = t.replace(f"# {h}", h)
        t = t.replace(f"{h}:", h)
    # Ensure each header is on its own line (LLM sometimes puts header + content on same line)
    import re as _re
    for h in _POSITIONING_HEADERS:
        t = _re.sub(rf"^({_re.escape(h)})\s+(?=[^\n])", rf"\1\n", t, flags=_re.MULTILINE)
    return t.strip()


def _positioning_sections_distinct(text: str) -> bool:
    """Return True if CORE PROBLEM and WHY CURRENT OPTIONS FAIL are meaningfully distinct.

    CORE PROBLEM = the user's lived friction.
    WHY CURRENT OPTIONS FAIL = the structural flaw in the alternative.
    They must not say the same thing.
    """
    problem_text = _section_first_line(text, "CORE PROBLEM", "CURRENT ALTERNATIVE")
    why_text = _section_first_line(text, "WHY CURRENT OPTIONS FAIL", "DESIRED OUTCOME")
    if not problem_text or not why_text:
        return True  # can't compare, let other validators handle missing sections
    # Exact match → fail
    if problem_text.strip().lower() == why_text.strip().lower():
        return False
    # High word overlap → fail
    p_words = set(problem_text.lower().split())
    w_words = set(why_text.lower().split())
    if not p_words or not w_words:
        return True
    overlap = len(p_words & w_words) / min(len(p_words), len(w_words))
    return overlap < 0.6


def _validate_positioning_output(text: str) -> bool:
    """Return True if positioning output has all required sections and no banned phrases."""
    if not text or len(text.strip()) < 300:
        return False
    if not _validate_headers(text, _POSITIONING_HEADERS):
        return False
    if _contains_banned_phrases(text, _POSITIONING_BANNED):
        return False
    if not _positioning_sections_distinct(text):
        return False
    return True


def score_positioning(text: str) -> dict:
    """Simple heuristic scoring for positioning output. Returns {score: float, notes: list}."""
    score = 10.0
    notes: List[str] = []
    t = (text or "").strip()
    for h in _POSITIONING_HEADERS:
        if h not in t:
            score -= 0.8
            notes.append(f"Missing section: {h}")
    if len(t) < 400:
        score -= 1.0
        notes.append("Output is very short; consider more detail.")
    if len(t) > 4000:
        score -= 0.5
        notes.append("Output is long; consider tightening.")
    for b in _POSITIONING_BANNED:
        if b in t.lower():
            score -= 0.5
            notes.append(f"Avoid: '{b}'")
    score = max(0.0, min(10.0, round(score, 1)))
    if score >= 8 and not notes:
        notes.append("All required sections present and concise.")
    return {"score": score, "notes": notes}


class PositioningWriterMixin:
    """Positioning decisions and positioning document generation.

    Mixed into WritingAgent; methods rely on its fields (brain_decisions,
    positioning, narrative) and may call methods from the other mixins.
    """

    def extract_positioning_decisions(self, brief: ClientBrief) -> dict:
        """Decision phase: extract positioning decisions from brief via ExtractionAgent.

        If brain_decisions are preloaded from product_profile.json (set by main.py after loading
        the Messaging Brain), they are returned immediately — no LLM call is made.

        Otherwise delegates to ExtractionAgent which handles the LLM call, retry, grounding,
        and fallback. Extraction logic lives in agents/extraction_agent.py.
        """
        if self.brain_decisions:
            _print_decisions_if_debug(self.brain_decisions)
            return self.brain_decisions

        from agents.extraction_agent import ExtractionAgent  # local import avoids circular dep
        return ExtractionAgent().run(brief)

    def write_positioning(self, brief: ClientBrief) -> str:
        """Generate a first-class positioning document grounded in the Messaging Brain.

        Uses pre-extracted brain decisions as the primary source of truth.
        Validates all 11 required sections. Retries with a stricter prompt on failure.
        Falls back to a brief-interpolated template only if LLM is unavailable or invalid.
        """
        decisions = self.extract_positioning_decisions(brief)

        product = clean_phrase(brief.product) or "Product"
        icp = decisions.get("icp") or brief.audience or "Target audience"
        primary_problem = decisions.get("primary_problem") or brief.pain or "Core problem"
        current_alternative = decisions.get("current_alternative") or ""
        desired_outcome = decisions.get("desired_outcome") or brief.offer or ""
        category_frame = decisions.get("category_frame") or ""
        differentiation = decisions.get("differentiation") or ""
        anti_positioning = decisions.get("anti_positioning") or ""
        tone = (brief.tone or "Clear, strategic, and direct").strip()

        system = (
            "You are a senior product strategist writing a positioning document. "
            "Write with strategic clarity. No hype. No buzzwords. No marketing filler. "
            "Each section must be concrete, specific to this product, and grounded in the decisions provided. "
            "CRITICAL: CORE PROBLEM and WHY CURRENT OPTIONS FAIL must be DISTINCT sections. "
            "CORE PROBLEM = the user's lived friction (what THEY experience). "
            "WHY CURRENT OPTIONS FAIL = the structural flaw in the ALTERNATIVE (why it was never designed for this). "
            "If they say the same thing, the document is invalid. "
            "Use exactly these section headers in this order, each on its own line: "
            "PRODUCT, ICP, CORE PROBLEM, CURRENT ALTERNATIVE, WHY CURRENT OPTIONS FAIL, "
            "DESIRED OUTCOME, CATEGORY FRAME, DIFFERENTIATION, ANTI-POSITIONING, "
            "POSITIONING STATEMENT, MESSAGING NOTES. "
            "No preamble. No markdown bold. No numbering. No extra headers. "
            "Banned words: streamline, empower, unlock, innovative, cutting-edge, revolutionize, "
            "best-in-class, game-changing, seamless, powerful solution, modern platform, "
            "all-in-one, ecosystem, synergy, leverage, disrupt."
        )
        user_parts = [
            "Write a positioning document for this product.",
            "",
            f"Product: {product}",
            f"Context: {brief.offer or brief.pain or 'Not specified'}",
            "",
            "POSITIONING DECISIONS (primary source of truth — use these to drive every section):",
            f"  ICP: {icp}",
            f"  Core Problem: {primary_problem}",
            f"  Current Alternative: {current_alternative or 'Infer from problem and audience'}",
            f"  Desired Outcome: {desired_outcome}",
            f"  Category Frame: {category_frame}",
            f"  Differentiation: {differentiation}",
            f"  Anti-Positioning: {anti_positioning}",
            "",
            "Instructions per section:",
            "PRODUCT — One sentence starting with the product name. What it is, factually. No adjectives like powerful or innovative.",
            "ICP — Who specifically this is for. Direct and specific. One sentence.",
            "CORE PROBLEM — The user's lived friction. What THEY experience day-to-day. Concrete, not abstract. One to two sentences. "
            "Do NOT mention alternatives or competitors here — focus only on the user's pain.",
            "CURRENT ALTERNATIVE — What users actually do today instead. Name it if possible. One sentence.",
            "WHY CURRENT OPTIONS FAIL — The STRUCTURAL FLAW in the current alternative. Why it was never designed for this. "
            "This must be different from CORE PROBLEM: CORE PROBLEM = user's pain, WHY CURRENT OPTIONS FAIL = the alternative's deficiency. "
            "One to three sentences.",
            "DESIRED OUTCOME — What the user actually wants. Specific. One sentence.",
            "CATEGORY FRAME — What kind of product this is. One phrase or short sentence.",
            "DIFFERENTIATION — Why this product works better. Grounded in mechanism, not claims. One to two sentences.",
            "ANTI-POSITIONING — What this product is NOT. What wrong frame to avoid. One to two sentences.",
            "POSITIONING STATEMENT — Two to three strong sentences for founder and product discussion. No fluff.",
            "MESSAGING NOTES — Three to five short bullets. How to talk about this product downstream.",
            "",
            f"Tone: {tone}",
        ]
        if brief.examples:
            user_parts.append(f"Examples (for grounding only): {brief.examples}")
        if brief.context:
            user_parts.append(f"Additional context: {brief.context}")
        user = "\n".join(user_parts)

        system_strict = (
            "You are a senior product strategist. Output a positioning document with EXACTLY these "
            "11 headers in order, each on its own line with content directly below: "
            "PRODUCT, ICP, CORE PROBLEM, CURRENT ALTERNATIVE, WHY CURRENT OPTIONS FAIL, "
            "DESIRED OUTCOME, CATEGORY FRAME, DIFFERENTIATION, ANTI-POSITIONING, "
            "POSITIONING STATEMENT, MESSAGING NOTES. "
            "No preamble. No markdown. No bold. No numbering. No extra headers. "
            "Banned: streamline, empower, unlock, innovative, cutting-edge, revolutionize, "
            "best-in-class, game-changing, seamless, powerful solution, modern platform."
        )

        def _valid(out: Optional[str]) -> bool:
            if not out:
                return False
            normalized = _normalize_positioning_output(out)
            return _validate_positioning_output(normalized)

        out = _run_with_retry(
            generate_fn=lambda: llm_generate(system=system, user=user, model="llama3:8b", temperature=0.3),
            strict_generate_fn=lambda: llm_generate(system=system_strict, user=user, model="llama3:8b", temperature=0.2),
            validator_fn=_valid,
        )
        if out and _valid(out):
            return (_normalize_positioning_output(out).rstrip("\n") + "\n")
        return self._write_positioning_fallback(brief, decisions)

    def _write_positioning_fallback(self, brief: ClientBrief, decisions: Optional[dict] = None) -> str:
        """Brief-interpolated positioning template using all 11 sections when LLM output is invalid."""
        d = decisions or {}
        product = clean_phrase(brief.product) or "Product"
        icp = d.get("icp") or clean_phrase(brief.audience) or "Target audience"
        primary_problem = d.get("primary_problem") or clean_sentence(brief.pain or "Core problem not yet articulated.")
        audience_lower = icp.lower().rstrip(".")
        current_alternative = (
            d.get("current_alternative")
            or f"Existing tools that {audience_lower} use today, not purpose-built for this problem."
        )
        offer = clean_phrase(brief.offer) or "A focused path to the outcome they need"
        desired_outcome = d.get("desired_outcome") or offer
        category_frame = d.get("category_frame") or f"{product} for {audience_lower}."
        differentiation = (
            d.get("differentiation")
            or f"Built specifically for {audience_lower} — not a general-purpose tool repurposed for this problem."
        )
        anti_positioning = (
            d.get("anti_positioning")
            or f"Not a broad platform trying to do everything. Focused on the specific problem {audience_lower} face."
        )
        offer_lower = lower_first(desired_outcome)
        # Keep a short label for alternatives (first sentence, max 60 chars)
        alt_first_sentence = current_alternative.split(".")[0] if current_alternative else "existing tools"
        alt_short = (alt_first_sentence[:60] + "...") if len(alt_first_sentence) > 60 else alt_first_sentence
        body = f"""PRODUCT
{product} is a focused tool for {audience_lower}.

ICP
{icp}

CORE PROBLEM
{primary_problem}

CURRENT ALTERNATIVE
{current_alternative}

WHY CURRENT OPTIONS FAIL
Current alternatives were not built for {audience_lower}. They address the general category but not the specific mechanics of the problem, leaving users to adapt tools that do not fit — adding friction and slowing outcomes.

DESIRED OUTCOME
{desired_outcome}

CATEGORY FRAME
{category_frame}

DIFFERENTIATION
{differentiation}

ANTI-POSITIONING
{anti_positioning}

POSITIONING STATEMENT
For {audience_lower}, {product} delivers {offer_lower}. It is purpose-built for this problem — not a general-purpose platform applied here. Where current alternatives fall short, {product} addresses the specific mechanics of how {audience_lower} actually need to work.

MESSAGING NOTES
- Lead with the specific problem: {primary_problem}
- Speak directly to {icp}
- Name what they use today: {alt_short}
- Differentiate on specificity: purpose-built, not repurposed
- Outcome language: {desired_outcome}
"""
        return (body.rstrip("\n") + "\n")
