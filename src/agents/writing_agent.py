import json
import os
import re
from dataclasses import dataclass
from typing import Callable, List, Optional

from core.model_provider import generate as llm_generate
from core.utils import clean_phrase, clean_sentence, lower_first


def _contains_banned_phrases(text: str, banned_list: tuple[str, ...]) -> bool:
    lower = (text or "").lower()
    return any(phrase in lower for phrase in banned_list)


def _validate_headers(text: str, required_headers: tuple[str, ...]) -> bool:
    t = (text or "").strip()
    return all(h in t for h in required_headers)


_UX_HEADERS = (
    "UX CONTEXT",
    "ONBOARDING",
    "EMPTY STATE",
    "ERROR",
    "TOAST",
    "BUTTON LABELS",
)
_UX_BANNED = (
    "streamline", "high-quality", "unlock", "revolutionize",
    "killer app", "you know the drill", "meh",
    "compelling", "drives conversions", "transform",
    "book a short working session", "request a rewrite", "paste your brief",
    "powerful solution", "modern platform", "seamless experience",
    "step complete", "move to the next stage",
    "next-generation", "next generation", "all-in-one", "innovative platform",
)
_UX_PLACEHOLDER_SUBSTRINGS = ("[insert", "[add", "insert context", "[context", "[product")

_UX_PRODUCT_BANNED = (
    "nothing here yet", "your list is empty", "something went wrong",
    "check your connection", "add your first",
    # Strategy-label leakage: LLM pasting positioning context verbatim into UI copy
    "desired outcome:", "differentiation:", "category frame:", "primary problem:",
    "instead of generating", "give you relevant results",
    # Generic SaaS filler in UX copy
    "step complete", "move to the next stage",
    # Generic SaaS workspace vocabulary that must never appear in product UX outputs
    "launch campaign", "campaign failed", "no campaign defined",
    "review progress", "add insights", "plan ready",
    "move to next stage",
)
# Domain-drift terms: generic SaaS nouns that signal the LLM has drifted into a generic template.
# These trigger regeneration in _validate_ux_output when target=="product".
_UX_DOMAIN_DRIFT = (
    "campaign",
    "workflow",
    "pipeline",
    "project",
    "ticket",
    "insight",
    "stage",
)
_UX_PRODUCT_SCENARIO_TAGS = ("[brief intake]", "[decision review]", "[generation review]")
_UX_PRODUCT_CONCRETE_ACTIONS = (
    "brief.json", "review decisions", "generate landing", "generate linkedin",
    "generate ux", "open latest", "validation failed", "ollama not running", "output saved",
)
# Operator workflow terms that must not appear in product-mode UX copy.
_UX_PRODUCT_OPERATOR_TERMS = (
    "brief.json", "generate landing", "generate linkedin", "generate ux",
    "open latest", "ollama not running", "output saved",
    "--brief", "--mode", "--client",
)

# ---------------------------------------------------------------------------
# Positioning document constants and validators
# ---------------------------------------------------------------------------

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


def _validate_positioning_output(text: str) -> bool:
    """Return True if positioning output has all required sections and no banned phrases."""
    if not text or len(text.strip()) < 300:
        return False
    if not _validate_headers(text, _POSITIONING_HEADERS):
        return False
    if _contains_banned_phrases(text, _POSITIONING_BANNED):
        return False
    return True


def _normalize_ux_output(raw: str) -> str:
    """Strip preamble, remove markdown bold from headers, remove UX WRITING PACK line."""
    if not raw or not raw.strip():
        return raw or ""
    t = raw.strip()
    idx = t.find("UX CONTEXT")
    if idx < 0:
        idx = t.find("**UX CONTEXT**")
    if idx > 0:
        t = t[idx:]
    for h in _UX_HEADERS:
        # Remove bold markers in all forms: **H**, **H, H**
        t = t.replace(f"**{h}**", h)
        t = t.replace(f"**{h}", h)
        t = t.replace(f"{h}**", h)
        # Remove trailing colons: "UX CONTEXT:" → "UX CONTEXT"
        t = t.replace(f"{h}:", h)
    lines = t.splitlines()
    out = []
    for line in lines:
        s = line.strip()
        if s.upper() == "UX WRITING PACK" or (s.startswith("**") and s.endswith("**") and "UX WRITING PACK" in s.upper()):
            continue
        out.append(line)
    return "\n".join(out).strip()


def _ux_domain_drift_cleanup(text: str) -> str:
    """Post-generation pass: replace generic SaaS patterns with product-native equivalents.

    This is a rule-based string substitution pass — it does not call the LLM.
    It catches common domain-drift phrases that slip through the banned list check.
    """
    if not text:
        return text
    replacements = (
        # Campaign drift
        ("Launch Campaign", "Generate Output"),
        ("launch campaign", "generate output"),
        ("Campaign failed", "Generation failed"),
        ("campaign failed", "generation failed"),
        ("No campaign defined", "No output defined yet"),
        ("no campaign defined", "no output defined yet"),
        ("No campaign brief yet", "No brief defined yet"),
        ("no campaign brief yet", "no brief defined yet"),
        ("No campaigns launched yet", "No outputs generated yet"),
        ("no campaigns launched yet", "no outputs generated yet"),
        ("Campaign launched", "Output generated"),
        ("campaign launched", "output generated"),
        ("Define Campaign", "Define Audience"),
        ("define campaign", "define audience"),
        # Insight drift
        ("Add Insights", "Build Brain"),
        ("add insights", "build brain"),
        ("Review Insights", "Review Output"),
        ("review insights", "review output"),
        # Workflow / pipeline / project drift
        ("No workflow yet", "No messaging brain yet"),
        ("no workflow yet", "no messaging brain yet"),
        ("your pipeline", "your output"),
        ("the pipeline", "the output"),
        # Review Progress drift
        ("Review Progress", "View Output"),
        ("review progress", "view output"),
        # Stage drift
        ("move to next stage", "continue"),
        ("move to the next stage", "continue"),
        ("Move to Next Stage", "Continue"),
        ("Move to the Next Stage", "Continue"),
        ("next stage", "next step"),
        ("Next Stage", "Next Step"),
        ("plan ready", "output ready"),
        ("Plan Ready", "Output Ready"),
    )
    result = text
    for old, new in replacements:
        result = result.replace(old, new)
    return result


def _section_first_line(text: str, header: str, next_header: str = "") -> str:
    """Return the first non-empty content line under a section header."""
    idx = text.find(header)
    if idx < 0:
        return ""
    after = text[idx + len(header):].lstrip("\n")
    if next_header:
        end = after.find(next_header)
        if end > 0:
            after = after[:end]
    lines = [ln.strip() for ln in after.splitlines() if ln.strip()]
    return lines[0] if lines else ""


def _validate_ux_output(text: str, target: Optional[str] = None) -> bool:
    """Check headers in order, counts (3,3,3,3,8), no banned phrases, no bracket placeholders. If target=='product', apply product-specific rules."""
    if not text or not text.strip():
        return False
    t = text.strip().lower()
    t_upper = text.upper()
    for h in _UX_HEADERS:
        if h not in t_upper:  # case-insensitive header presence
            return False
    pos = 0
    for h in _UX_HEADERS:
        i = t_upper.find(h, pos)
        if i < 0:
            return False
        pos = i + len(h)
    if _contains_banned_phrases(text, _UX_BANNED):
        return False
    for p in _UX_PLACEHOLDER_SUBSTRINGS:
        if p in t:
            return False
    # Count items per section: ONBOARDING 3, EMPTY STATE 3, ERROR 3, TOAST 3, BUTTON LABELS 8
    sections = ("ONBOARDING", "EMPTY STATE", "ERROR", "TOAST", "BUTTON LABELS")
    expected = (3, 3, 3, 3, 8)
    for sect, exp in zip(sections, expected):
        start = text.find(sect)
        if start < 0:
            return False
        end = len(text)
        for next_s in sections:
            if next_s != sect:
                j = text.find(next_s, start + 1)
                if 0 <= j < end:
                    end = j
        block = text[start:end]
        numbered = [x for x in block.splitlines() if x.strip() and x.strip()[0].isdigit()]
        if len(numbered) < exp:
            return False

    # Button label word count: each label must be ≤ 4 words
    bl_start = text.find("BUTTON LABELS")
    if bl_start >= 0:
        bl_block = text[bl_start:bl_start + 400]
        bl_lines = [x.strip() for x in bl_block.splitlines() if x.strip() and x.strip()[0].isdigit()]
        for lbl_line in bl_lines:
            lbl = re.sub(r"^\d+\.\s*", "", lbl_line).strip()
            if len(lbl.split()) > 4:
                return False

    if target == "product":
        if _contains_banned_phrases(text, _UX_PRODUCT_BANNED):
            return False
        if _contains_banned_phrases(t, _UX_PRODUCT_OPERATOR_TERMS):
            return False
        if _contains_banned_phrases(t, _UX_DOMAIN_DRIFT):
            return False
        if "TARGET: product" not in text and "target: product" not in t:
            return False
    return True


def _run_with_retry(
    generate_fn: Callable[[], Optional[str]],
    strict_generate_fn: Callable[[], Optional[str]],
    validator_fn: Callable[[Optional[str]], bool],
) -> Optional[str]:
    try:
        out = generate_fn()
        if validator_fn(out):
            return out
        out = strict_generate_fn()
        if validator_fn(out):
            return out
    except Exception:
        return None
    return None


def _print_decisions_if_debug(decisions: dict) -> None:
    if os.getenv("DEBUG_DECISIONS", "").lower() != "true":
        return
    ordered = (
        ("ICP", "icp"),
        ("Primary Problem", "primary_problem"),
        ("Current Alternative", "current_alternative"),
        ("Desired Outcome", "desired_outcome"),
        ("Category Frame", "category_frame"),
        ("Differentiation", "differentiation"),
        ("Anti-Positioning", "anti_positioning"),
    )
    print("— POSITIONING DECISIONS —")
    for label, key in ordered:
        print(f"{label}: {decisions.get(key, '')}")


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


@dataclass
class ClientBrief:
    product: str
    audience: str
    pain: str
    offer: str
    tone: str
    cta: str
    examples: Optional[str] = ""
    context: Optional[str] = ""


@dataclass
class WritingAgent:
    name: str = "WritingAgent"
    # Preloaded positioning decisions from product_profile.json (the Messaging Brain).
    # When set, extract_positioning_decisions() uses these directly instead of calling the LLM.
    brain_decisions: Optional[dict] = None

    def write_landing_page(self, brief: ClientBrief) -> str:
        """Generate landing page from positioning decisions via LLM; fallback to rule-based template if invalid."""
        decisions = self.extract_positioning_decisions(brief)

        _LANDING_HEADERS = (
            "HEADLINE", "SUBHEAD", "WHO ITS FOR", "PROBLEM", "WHY CURRENT OPTIONS FAIL",
            "WHAT THIS IS", "DIFFERENTIATION", "PROOF / SIGNALS", "CTA",
        )
        _LANDING_BANNED = (
            "streamline", "empower", "unlock", "innovative", "cutting-edge", "revolutionize",
            "best-in-class", "game-changing", "stunning", "incredible", "amazing",
            "generic options", "modern platform", "powerful solution", "next generation",
            "seamless experience", "innovative platform", "generic platform",
            "end-to-end", "all-in-one", "game changer", "paradigm",
            "book a short working session", "paste your brief", "request a rewrite",
            "under an hour", "within minutes", "in under", "in minutes",
            "sign up today", "get started today", "step complete", "move to the next stage",
        )

        def _headline_has_question(text: str) -> bool:
            t = (text or "").strip()
            if "HEADLINE" not in t:
                return False
            idx = t.find("HEADLINE")
            end = t.find("\n\n", idx) if idx >= 0 else -1
            block = t[idx : end if end > 0 else len(t)]
            return "?" in block

        def _headline_ok(text: str) -> bool:
            """Headline content line must be ≤ 12 words."""
            first = _section_first_line(text, "HEADLINE", "SUBHEAD")
            return len(first.split()) <= 12 if first else True

        def _subhead_ok(text: str) -> bool:
            """Subhead content line must be ≤ 25 words."""
            first = _section_first_line(text, "SUBHEAD", "WHO ITS FOR")
            return len(first.split()) <= 25 if first else True

        def _valid(out: str) -> bool:
            return (
                bool(out)
                and _validate_headers(out, _LANDING_HEADERS)
                and not _contains_banned_phrases(out, _LANDING_BANNED)
                and not _headline_has_question(out)
                and _headline_ok(out)
                and _subhead_ok(out)
            )

        icp = decisions.get("icp", "")
        primary_problem = decisions.get("primary_problem", "")
        current_alternative = decisions.get("current_alternative", "")
        desired_outcome = decisions.get("desired_outcome", "")
        category_frame = decisions.get("category_frame", "")
        differentiation = decisions.get("differentiation", "")
        anti_positioning = decisions.get("anti_positioning", "")

        system = (
            "You are a senior product marketer and UX writer. "
            "Write first-class product messaging for a real product launch. Every section must express the actual product — no templates. "
            "HEADLINE: ≤ 12 words. A sharp, memorable declarative statement of what this product enables. "
            "  NOT a sentence about the ICP. NOT 'For [ICP] who struggle to...'. NOT a slogan. NOT a question. "
            "  Good example: 'Turn messy product ideas into clear messaging.' — that kind of concision and specificity. "
            "SUBHEAD: ≤ 25 words. One sentence. Explain the product clearly — category + how it solves the problem. No filler. "
            "WHO ITS FOR: Maximum 2 short sentences. Describe the ICP directly. No emotional storytelling, no 'You know the feeling'. "
            "PROBLEM: concrete, specific friction. Name the real pain — no abstract claims. "
            "WHY CURRENT OPTIONS FAIL: name the specific current alternative. Explain exactly where it falls short. "
            "  Never write 'generic options fail'. Name the gap specifically. "
            "WHAT THIS IS: define the product category. Explain the core mechanism briefly. "
            "DIFFERENTIATION: lead with the differentiation, close with what this is NOT. "
            "PROOF / SIGNALS: one believable neutral claim. "
            "  NEVER write specific time claims ('under an hour', 'in minutes', 'within 5 minutes'). "
            "  Use: 'Early users report clearer messaging after their first session.' or 'Teams quickly align on product language.' "
            "CTA: product-specific action verb tied to the desired outcome. One short line. "
            "  Not 'Sign up today'. Not 'Get started today'. Make it specific to what this product delivers. "
            "Banned phrases: streamline, empower, unlock, innovative, cutting-edge, revolutionize, best-in-class, game-changing, "
            "generic options, modern platform, powerful solution, next generation, seamless experience, all-in-one, under an hour, in minutes. "
            "Output EXACT headers in this order: HEADLINE, SUBHEAD, WHO ITS FOR, PROBLEM, "
            "WHY CURRENT OPTIONS FAIL, WHAT THIS IS, DIFFERENTIATION, PROOF / SIGNALS, CTA. "
            "One block of content under each. No preamble. No explanation. Output only the document."
        )
        system_strict = (
            "Senior product marketer. STRICT output only. "
            "HEADLINE: ≤ 12 words. Sharp declarative statement of the product outcome. Not a description of the ICP. Not a question. "
            "SUBHEAD: ≤ 25 words. One sentence. Category + how it solves the problem. "
            "WHO ITS FOR: max 2 sentences. Direct ICP description, no emotional framing. "
            "PROBLEM: concrete friction, no abstraction. "
            "WHY CURRENT OPTIONS FAIL: name the specific alternative, explain the gap — not 'generic options'. "
            "DIFFERENTIATION: direct, then contrast against anti-positioning. "
            "PROOF / SIGNALS: neutral believable claim — NO time claims ('under an hour', 'in minutes'), NO invented percentages. "
            "CTA: one line, product-specific verb. Not 'Sign up today'. "
            "Headers in order: HEADLINE, SUBHEAD, WHO ITS FOR, PROBLEM, WHY CURRENT OPTIONS FAIL, WHAT THIS IS, DIFFERENTIATION, PROOF / SIGNALS, CTA. "
            "No hype words. No banned phrases. Output only the document."
        )
        user_parts = [
            "You are a senior product marketer and UX writer.",
            "",
            "Write a landing page for the following product. Express these positioning decisions directly — not as a template. Every word must reflect the actual product.",
            "",
            f"Product: {brief.product or 'Not specified'}",
            "",
            "Positioning Decisions:",
            f"  ICP: {icp}",
            f"  Primary Problem: {primary_problem}",
            f"  Current Alternative: {current_alternative}",
            f"  Desired Outcome: {desired_outcome}",
            f"  Category Frame: {category_frame}",
            f"  Differentiation: {differentiation}",
            f"  Anti-Positioning: {anti_positioning}",
            "",
            f"Tone: {brief.tone or 'Clear and direct'}",
            "",
            "Per-section instructions (do not include these in output):",
            f"  HEADLINE: ≤ 12 words. A sharp, memorable statement of what this product enables. "
            f"  Do NOT start with '{icp}' or describe the ICP — instead express the outcome concisely. "
            f"  Think: short, specific, declarative. No slogans. No questions.",
            f"  SUBHEAD: ≤ 25 words. One sentence. Explain what {brief.product or 'the product'} is and how it solves the problem. Include the category frame ({category_frame}).",
            f"  WHO ITS FOR: Maximum 2 sentences. Name {icp} directly. Describe their situation concretely. No emotional storytelling.",
            f"  PROBLEM: State '{primary_problem}' without abstraction. Name the real friction. Be specific.",
            f"  WHY CURRENT OPTIONS FAIL: Explain specifically why {current_alternative or 'the current alternative'} falls short. Name the gap. Do not write 'generic options fail'.",
            f"  WHAT THIS IS: State the category frame ({category_frame}). Briefly explain the core mechanism.",
            f"  DIFFERENTIATION: Lead with '{differentiation}'. Close with a contrast against '{anti_positioning}'.",
            "  PROOF / SIGNALS: One believable, neutral signal. NEVER write specific time claims ('under an hour', 'in minutes', 'within X minutes'). Use: 'Early users report...' or 'Teams quickly...'",
            f"  CTA: One short action line tied to '{desired_outcome}'. Use a concrete product-specific verb. Not 'Sign up today'.",
            "",
            "Output format (exact headers in this order): HEADLINE, SUBHEAD, WHO ITS FOR, PROBLEM, "
            "WHY CURRENT OPTIONS FAIL, WHAT THIS IS, DIFFERENTIATION, PROOF / SIGNALS, CTA.",
        ]
        user = "\n".join(user_parts)

        out = _run_with_retry(
            generate_fn=lambda: llm_generate(system=system, user=user, model="llama3:8b", temperature=0.3),
            strict_generate_fn=lambda: llm_generate(system=system_strict, user=user, model="llama3:8b", temperature=0.25),
            validator_fn=_valid,
        )
        if out:
            return (out.rstrip("\n") + "\n")
        return self._write_landing_page_fallback(brief, decisions)

    def _write_landing_page_fallback(self, brief: ClientBrief, decisions: dict) -> str:
        """Rule-based landing template with new headers when LLM invalid or unavailable."""
        icp = decisions.get("icp", "") or clean_phrase(brief.audience) or "Your ideal customers"
        problem = decisions.get("primary_problem", "") or clean_sentence(brief.pain or "Core problem not articulated.")
        alternative_raw = decisions.get("current_alternative", "") or clean_phrase(brief.pain or "") or ""
        alternative = alternative_raw if alternative_raw else f"Existing tools that don't address {icp.lower().rstrip('.')} specifically."
        outcome = decisions.get("desired_outcome", "") or clean_phrase(brief.offer) or "Clear messaging that converts."
        category = decisions.get("category_frame", "") or f"{clean_phrase(brief.product) or 'Product'} for {icp}."
        diff = decisions.get("differentiation", "") or clean_phrase(brief.offer) or "Focused on this outcome."
        product = clean_phrase(brief.product) or "This product"
        cta = clean_sentence(brief.cta) if brief.cta else f"Get started with {product}."
        proof = clean_phrase(brief.examples or "") or ""
        proof_block = f"From the brief: {proof}" if proof else "Early users complete their first step in minutes."
        body = f"""HEADLINE
{product}: {outcome}

SUBHEAD
For {icp}. {problem}

WHO ITS FOR
{icp}

PROBLEM
{problem}

WHY CURRENT OPTIONS FAIL
{alternative}

WHAT THIS IS
{category}

DIFFERENTIATION
{diff}

PROOF / SIGNALS
{proof_block}

CTA
{cta}
"""
        return (body.rstrip("\n") + "\n")

    def rewrite_landing_page(self, brief: ClientBrief, draft: str, critique: dict) -> str:
        """Senior editor pass: tighten headline, compress subhead, remove repetition.

        If the draft has valid structure, runs an LLM editorial pass to sharpen it.
        Falls back to the original draft if the rewrite fails validation.
        Emergency fallback if the draft is structurally broken.
        """
        _LANDING_HEADERS = (
            "HEADLINE", "SUBHEAD", "WHO ITS FOR", "PROBLEM", "WHY CURRENT OPTIONS FAIL",
            "WHAT THIS IS", "DIFFERENTIATION", "PROOF / SIGNALS", "CTA",
        )
        _LANDING_BANNED = (
            "streamline", "empower", "unlock", "innovative", "cutting-edge", "revolutionize",
            "best-in-class", "game-changing", "stunning", "incredible", "amazing",
            "generic options", "modern platform", "powerful solution", "next generation",
            "seamless experience", "innovative platform", "generic platform",
            "end-to-end", "all-in-one", "game changer", "paradigm",
            "book a short working session", "paste your brief", "request a rewrite",
            "under an hour", "within minutes", "in under", "in minutes",
            "sign up today", "get started today", "step complete", "move to the next stage",
        )

        if not draft or not _validate_headers(draft, _LANDING_HEADERS):
            # Emergency fallback: structurally broken draft
            product = clean_phrase(brief.product) or "Your product"
            audience = clean_phrase(brief.audience) or "your audience"
            pain = clean_sentence(brief.pain or "The core problem is not yet described.")
            offer = clean_phrase(brief.offer) or "a focused solution"
            cta = clean_sentence(brief.cta) if brief.cta else f"Get started with {product}."
            return (f"HEADLINE\n{product}: {offer}\n\n"
                    f"SUBHEAD\nFor {audience}. {pain}\n\n"
                    f"WHO ITS FOR\n{audience}\n\n"
                    f"PROBLEM\n{pain}\n\n"
                    f"WHY CURRENT OPTIONS FAIL\n"
                    f"Current tools {audience.lower()} rely on were not built for {offer.lower()}. "
                    f"They cover the category broadly but miss the specific friction {audience.lower()} face.\n\n"
                    f"WHAT THIS IS\n{product} is a dedicated tool for {audience.lower()}.\n\n"
                    f"DIFFERENTIATION\n{offer}.\n\n"
                    f"PROOF / SIGNALS\nEarly users reach {offer.lower()} without the overhead of general-purpose alternatives.\n\n"
                    f"CTA\n{cta}\n")

        # LLM senior editor pass: tighten and sharpen without replacing product-specific language
        editor_system = (
            "You are a senior editor reviewing a product landing page draft. "
            "Your job: tighten and sharpen. Do NOT replace product-specific language with generic templates. "
            "RULES:\n"
            "1. HEADLINE: must be ≤ 12 words. Cut aggressively. A sharp outcome statement, not an ICP description.\n"
            "2. SUBHEAD: must be ≤ 25 words. One sentence. Keep category + problem-to-outcome arc.\n"
            "3. WHO ITS FOR: maximum 2 sentences. Remove emotional storytelling. State the ICP directly.\n"
            "4. PROOF / SIGNALS: remove any specific time claims ('under an hour', 'in minutes', 'within X'). Replace with 'Early users report...' or similar neutral phrasing.\n"
            "5. CTA: one line. Remove 'Sign up today' or 'Get started today'. Use a product-specific action.\n"
            "6. Remove repetition across sections — if a phrase appears in multiple sections, cut it from the weaker one.\n"
            "7. Keep all 9 headers in the exact same order. Return only the full revised document. No preamble. No explanation."
        )
        editor_user = f"Tighten and sharpen this landing page:\n\n{draft}"
        try:
            rewritten = llm_generate(system=editor_system, user=editor_user, model="llama3:8b", temperature=0.15)
            if (rewritten
                    and _validate_headers(rewritten, _LANDING_HEADERS)
                    and not _contains_banned_phrases(rewritten, _LANDING_BANNED)):
                return (rewritten.rstrip("\n") + "\n")
        except Exception:
            pass

        # Editor pass failed — return original draft (already valid from write_landing_page)
        return (draft.rstrip("\n") + "\n")

    def write_linkedin_post(self, brief: ClientBrief) -> str:
        """Generate LinkedIn post from positioning decisions via Ollama; fall back to rule-based if unavailable."""
        decisions = self.extract_positioning_decisions(brief)

        _LINKEDIN_BANNED = (
            "high-quality", "on-demand", "streamline", "solutions", "like you",
            "designed for", "transform", "unlock", "revolutionize",
            "empower", "innovative", "cutting-edge", "game-changing", "best-in-class",
            "meh", "killer app", "you know the drill",
            "you're not alone", "ready to", "turn your", "drives results", "compelling message",
        )

        def _normalize_headers(text: str) -> str:
            out = text
            for h in ("HOOK", "PROBLEM", "INSIGHT", "SOFT PITCH", "CTA"):
                out = out.replace(f"**{h}**", h)
            return (out.rstrip("\n") + "\n")

        system = (
            "You are a B2B messaging strategist. Write clearly and sharply. No hype. "
            "No vague SaaS clichés. No storytelling fluff. "
            "HOOK must be a concrete observation—no 'Struggling to…', no 'You're not alone'. "
            "CTA must be one line only—no 'Ready to… Let us…' or two-sentence CTAs. "
            "Do NOT use: streamline, empower, unlock, innovative, cutting-edge, game-changing, best-in-class, "
            "meh, killer app, you know the drill, you're not alone, ready to, turn your, drives results, compelling message. "
            "Keep sentences short. Use concrete language. Do not use quotes. "
            "Use EXACT headers in this order: HOOK, PROBLEM, INSIGHT, SOFT PITCH, CTA. "
            "Output only the post with those headers and one block of content under each. No preamble."
        )
        system_strict = (
            "B2B messaging strategist. HOOK: concrete observation only (no 'Struggling to…', no 'You're not alone'). "
            "CTA: exactly one line (no 'Ready to… Let us…'). "
            "Banned: streamline, empower, unlock, innovative, cutting-edge, game-changing, best-in-class, "
            "meh, killer app, you know the drill, you're not alone, ready to, turn your, drives results, compelling message. "
            "Short sentences. No quotes. Headers: HOOK, PROBLEM, INSIGHT, SOFT PITCH, CTA. Output only the post."
        )
        user_parts = [
            "Write a short LinkedIn post using ONLY the positioning decisions below.",
            "",
            "Positioning Decisions:",
            f"  ICP: {decisions.get('icp', '')}",
            f"  Primary Problem: {decisions.get('primary_problem', '')}",
            f"  Current Alternative: {decisions.get('current_alternative', '')}",
            f"  Desired Outcome: {decisions.get('desired_outcome', '')}",
            f"  Category Frame: {decisions.get('category_frame', '')}",
            f"  Differentiation: {decisions.get('differentiation', '')}",
            f"  Anti-Positioning: {decisions.get('anti_positioning', '')}",
            "",
            f"User custom instructions (tone): {brief.tone or 'Clear and direct'}",
            "",
            "Instructions:",
            "  HOOK must focus on the primary_problem.",
            "  PROBLEM must mention current_alternative.",
            "  INSIGHT must explain why the current alternative fails.",
            "  SOFT PITCH must clearly reference category_frame and differentiation.",
            "  CTA must connect to desired_outcome.",
            "",
            "Output format (exact headers in this order): HOOK, PROBLEM, INSIGHT, SOFT PITCH, CTA.",
        ]
        user = "\n".join(user_parts)

        try:
            out = llm_generate(system=system, user=user, model="llama3:8b", temperature=0.4)
            if out and "HOOK" in out and "CTA" in out:
                if _contains_banned_phrases(out, _LINKEDIN_BANNED):
                    out = llm_generate(
                        system=system_strict, user=user, model="llama3:8b", temperature=0.3
                    )
                if out and "HOOK" in out and "CTA" in out:
                    return _normalize_headers(out)
        except Exception:
            pass
        return self._write_linkedin_post_rulebased(brief)

    def _write_linkedin_post_rulebased(self, brief: ClientBrief) -> str:
        """Fallback rule-based LinkedIn post when LLM is unavailable."""
        product = clean_phrase(brief.product) or "Your product"
        audience_phrase = clean_phrase(brief.audience) or "your ideal customers"
        pain_sentence = clean_sentence(
            brief.pain or "Most teams struggle to explain their product in a single, clear scroll."
        )
        offer_phrase = lower_first(
            clean_phrase(brief.offer) or "clear, high-conversion messaging"
        )
        tone_phrase = lower_first(clean_phrase(brief.tone) or "clear, confident, and human")
        cta = clean_sentence(
            brief.cta
            or "If you want a teardown of your current page, comment 'TEARDOWN' or send a quick DM."
        )

        hook = (
            f"{product} does not need more features. "
            f"It needs clearer words for {audience_phrase}."
        )

        problem = (
            f"{pain_sentence} Right now, visitors skim your page, nod along, and still do not feel "
            "the moment when your product actually helps them."
        )

        insight = (
            "The pages that convert are not the ones with the most sections. "
            f"They are the ones that name a sharp problem, show a concrete outcome, "
            f"and speak in a {tone_phrase} voice instead of generic SaaS jargon."
        )

        soft_pitch = (
            f"If you want, I can help you with {offer_phrase} "
            f"so {audience_phrase} understand it on the first read."
        )

        body = f"""
HOOK
{hook}

PROBLEM
{problem}

INSIGHT
{insight}

SOFT PITCH
{soft_pitch}

CTA
{cta}
""".rstrip()

        return body + "\n"

    def rewrite_linkedin_post(self, brief: ClientBrief, draft: str, strategy: dict) -> str:
        """Rule-based LinkedIn rewrite: stronger hook, tighter problem, clean soft pitch, sharp CTA."""
        if not draft or not draft.strip():
            return draft

        # --- Parse sections (preserve headers and order) ---
        section_headers = ("HOOK", "PROBLEM", "INSIGHT", "SOFT PITCH", "CTA")
        sections: dict[str, str] = {}
        lines = draft.splitlines()
        current_header: Optional[str] = None
        current_body: list[str] = []

        for line in lines:
            stripped = line.strip()
            if stripped in section_headers:
                if current_header is not None:
                    sections[current_header] = "\n".join(current_body).strip()
                current_header = stripped
                current_body = []
            elif current_header is not None:
                current_body.append(line)
        if current_header is not None:
            sections[current_header] = "\n".join(current_body).strip()

        product = clean_phrase(brief.product) or "Your product"
        audience_phrase = clean_phrase(brief.audience) or "your ideal customers"
        audience_phrase = lower_first(audience_phrase)
        tone_phrase = lower_first(clean_phrase(brief.tone) or "clear, confident, and human")
        offer_raw = clean_phrase(brief.offer) or "clear, high-conversion messaging"

        # --- 1) HOOK IMPROVEMENT ---
        def _improve_hook(hook_text: str) -> str:
            negative_phrases = ("does not need more features", "doesn't need more features", "do not need")
            lower = (hook_text or "").lower()
            if any(p in lower for p in negative_phrases) or " need " in lower and " not " in lower:
                # Stronger positioning: max 2 sentences, no hype
                return f"{product} helps {audience_phrase} explain what they actually built."
            return hook_text

        hook_content = sections.get("HOOK", "")
        sections["HOOK"] = _improve_hook(hook_content)

        # --- 2) PROBLEM TIGHTENING ---
        def _tighten_problem(problem_text: str) -> str:
            # Phrase → replacement (shorten without breaking grammar)
            fillers = (
                ("right now, ", " "),
                ("right now ", " "),
                (" and still do not feel the moment when ", " and don't feel when "),
                (" and still don't feel the moment when ", " and don't feel when "),
                (" the moment when ", " when "),
            )
            text = (problem_text or "").strip()
            for sep in (". ", "! ", "? "):
                text = text.replace(sep, sep[0] + "\n")
            raw_sentences = [s.strip() for s in text.split("\n") if s.strip()]
            kept = []
            for s in raw_sentences:
                if len(kept) >= 2:
                    break
                if not s:
                    continue
                if s[-1] not in ".!?":
                    s = s + "."
                lower = s.lower()
                for old, new in fillers:
                    lower = lower.replace(old, new)
                s_clean = " ".join(lower.split()).strip()
                if not s_clean:
                    continue
                s_clean = s_clean[0].upper() + s_clean[1:]
                kept.append(s_clean)
            return " ".join(kept).strip() if kept else problem_text

        sections["PROBLEM"] = _tighten_problem(sections.get("PROBLEM", ""))

        # --- 3) SOFT PITCH CLEANUP ---
        def _clean_soft_pitch() -> str:
            offer_phrase = lower_first(clean_phrase(offer_raw) or "clear, high-conversion messaging")
            # "operator" max once; no duplicated offer fragments
            words = offer_phrase.split()
            seen_operator = False
            deduped = []
            for w in words:
                if w.lower() == "operator":
                    if not seen_operator:
                        deduped.append(w)
                        seen_operator = True
                else:
                    deduped.append(w)
            offer_phrase = " ".join(deduped)
            return f"If you want, I can help you with {offer_phrase} so {audience_phrase} understand it immediately."

        sections["SOFT PITCH"] = _clean_soft_pitch()

        # --- 4) CTA SHARPENING ---
        if strategy.get("cta_improvements"):
            sections["CTA"] = "Book a short working session and leave with clearer messaging."
        # else: keep existing CTA content in sections["CTA"]

        # --- Rebuild post (same headers, same order) ---
        out_lines: list[str] = []
        for header in section_headers:
            body = sections.get(header, "")
            out_lines.append(header)
            if body:
                out_lines.append(body)
            out_lines.append("")

        result = "\n".join(out_lines).rstrip("\n") + "\n"
        return result

    def write_ux_microcopy(self, brief: ClientBrief) -> str:
        """Generate UX microcopy options: onboarding, empty state, error, confirmation toast."""
        product = clean_phrase(brief.product) or "Your product"
        audience = clean_phrase(brief.audience) or "your users"
        audience = lower_first(audience)
        tone_phrase = lower_first(clean_phrase(brief.tone) or "clear and friendly")

        onboarding = [
            f"Welcome. {product} helps {audience} get to the outcome faster.",
            f"First time here? Set up your first step in under a minute.",
            f"Let's get you started. You're three steps from your first result.",
        ]
        empty_state = [
            f"Nothing here yet. Add your first item to see how {product} works.",
            f"Your list is empty. Create something to get started.",
            f"No data yet. Once you add items, they'll show up here.",
        ]
        error_msg = [
            "Something went wrong. Please try again in a moment.",
            "We couldn't complete that. Check your connection and retry.",
            "Action failed. If this keeps happening, contact support.",
        ]
        confirmation = [
            "Done. Your changes are saved.",
            "Saved. You can keep editing or leave.",
        ]

        body = f"""ONBOARDING
{chr(10).join(onboarding)}

EMPTY STATE
{chr(10).join(empty_state)}

ERROR MESSAGE
{chr(10).join(error_msg)}

CONFIRMATION TOAST
{chr(10).join(confirmation)}
"""
        return (body.rstrip("\n") + "\n")

    def rewrite_ux_microcopy(self, brief: ClientBrief, draft: str, strategy: dict) -> str:
        """Rule-based pass: keep structure; optionally apply strategy notes as comments or leave draft unchanged."""
        if not draft or not strategy:
            return draft
        # Preserve section structure; no reorder. Strategy can be used later for hints.
        return draft

    def write_launch_pack(self, brief: ClientBrief) -> str:
        """Generate launch pack: teaser, social post, 5-tweet thread, app store subtitle."""
        product = clean_phrase(brief.product) or "Your product"
        audience = clean_phrase(brief.audience) or "your audience"
        audience = lower_first(audience)
        offer_phrase = lower_first(clean_phrase(brief.offer) or "the outcome they need")

        teaser = f"{product} — for {audience} who want {offer_phrase}."
        social = (
            f"We built {product} for {audience}. "
            f"It's built around one thing: {offer_phrase}. "
            "If that's you, we'd love your feedback."
        )
        thread = [
            f"1. {product} is for {audience}.",
            f"2. The problem: most tools don't help you {offer_phrase}.",
            f"3. We focused on one outcome: get from brief to clear message fast.",
            "4. No fluff. No generic templates. Just your story, sharp.",
            f"5. If that resonates, try {product}. Link in bio.",
        ]
        app_store = f"{product}: {offer_phrase} for {audience}."

        body = f"""TEASER LINE
{teaser}

SOCIAL POST
{social}

5-TWEET THREAD
{chr(10).join(thread)}

APP STORE SUBTITLE
{app_store}
"""
        return (body.rstrip("\n") + "\n")

    def rewrite_launch_pack(self, brief: ClientBrief, draft: str, strategy: dict) -> str:
        """Rule-based pass: keep structure and headers; no reorder."""
        if not draft or not strategy:
            return draft
        return draft

    def extract_positioning_decisions(self, brief: ClientBrief) -> dict:
        """Decision phase: extract positioning decisions as strict JSON; fallback to brief-derived dict if invalid.

        If brain_decisions are preloaded from product_profile.json (set by main.py after loading the
        Messaging Brain), they are returned immediately — no LLM call is made.
        """
        if self.brain_decisions:
            _print_decisions_if_debug(self.brain_decisions)
            return self.brain_decisions

        _DECISION_KEYS = (
            "icp", "primary_problem", "current_alternative", "desired_outcome",
            "category_frame", "differentiation", "anti_positioning",
        )
        _BANNED = (
            "streamline", "empower", "unlock", "innovative", "cutting-edge",
            "revolutionize", "best-in-class",
        )

        def _parse_and_validate(raw: str) -> Optional[dict]:
            if not raw or not raw.strip():
                return None
            raw = raw.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                start = next((i for i, l in enumerate(lines) if "{" in l), 0)
                end = next((i for i in range(len(lines) - 1, -1, -1) if "}" in lines[i]), len(lines))
                raw = "\n".join(lines[start : end + 1])
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return None
            if not isinstance(data, dict):
                return None
            for k in _DECISION_KEYS:
                if k not in data or not isinstance(data.get(k), str):
                    return None
            result = {k: (data[k] or "").strip() for k in _DECISION_KEYS}
            if not all(result[k] for k in _DECISION_KEYS):
                return None  # empty field — cannot propagate to generation
            combined = " ".join(result[k] for k in _DECISION_KEYS)
            if _contains_banned_phrases(combined, _BANNED):
                return None
            return result

        system = (
            "You are a product positioning strategist. "
            "Make concrete strategic decisions. No marketing tone. No storytelling. No hype language. "
            "Output must be STRICT JSON only. No markdown. No explanation text. No extra keys. No headings."
        )
        system_strict = (
            "You are a product positioning strategist. Output ONLY valid JSON. "
            "No markdown, no code fences, no explanation, no extra keys. "
            "Exactly 7 keys: icp, primary_problem, current_alternative, desired_outcome, category_frame, differentiation, anti_positioning. "
            "Each value: one short concrete sentence. "
            "Banned words: streamline, empower, unlock, innovative, cutting-edge, revolutionize, best-in-class."
        )
        tone_instruction = (brief.tone or "Clear and direct").strip()
        user_parts = [
            "Extract positioning decisions from this brief.",
            f"product: {brief.product or 'Not specified'}",
            f"audience: {brief.audience or 'Not specified'}",
            f"pain: {brief.pain or 'Not specified'}",
            f"offer: {brief.offer or 'Not specified'}",
            f"User custom instructions (tone): {tone_instruction}",
        ]
        if brief.examples:
            user_parts.append(f"examples: {brief.examples}")
        if brief.context:
            user_parts.append(f"context: {brief.context}")
        user_parts.append(
            "Return valid JSON with EXACTLY these keys (each value a short, concrete sentence): "
            "icp, primary_problem, current_alternative, desired_outcome, category_frame, differentiation, anti_positioning. "
            "Do NOT use vague words: streamline, empower, unlock, innovative, cutting-edge, revolutionize, best-in-class."
        )
        user = "\n".join(user_parts)

        parsed = _run_with_retry(
            generate_fn=lambda: _parse_and_validate(
                llm_generate(system=system, user=user, model="llama3:8b", temperature=0.2)
            ),
            strict_generate_fn=lambda: _parse_and_validate(
                llm_generate(system=system_strict, user=user, model="llama3:8b", temperature=0.15)
            ),
            validator_fn=lambda d: d is not None,
        )
        if parsed is not None:
            parsed, _ = GroundingAgent().ground(parsed, brief)
            _print_decisions_if_debug(parsed)
            return parsed
        fallback = self._extract_positioning_decisions_fallback(brief)
        _print_decisions_if_debug(fallback)
        return fallback

    def _extract_positioning_decisions_fallback(self, brief: ClientBrief) -> dict:
        """Fallback decision dict from brief when LLM output is invalid."""
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
            "desired_outcome": clean_sentence(offer) if offer else f"{product} helps {audience_lower} reach the outcome they care about.",
            "category_frame": f"{product} for {audience_lower}.",
            "differentiation": (
                f"Built specifically for {audience_lower} — not a general-purpose tool repurposed for this problem. "
                f"Focused entirely on {offer_lower}."
            ),
            "anti_positioning": (
                f"Not a broad platform trying to do everything. "
                f"Designed around the specific problem {audience_lower} face, not the category they sit in."
            ),
        }

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
            "CORE PROBLEM — The real friction. Concrete, not abstract. One to two sentences.",
            "CURRENT ALTERNATIVE — What users actually do today instead. Name it if possible. One sentence.",
            "WHY CURRENT OPTIONS FAIL — Specific weaknesses of that alternative. One to three sentences.",
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

    def write_ux_pack(self, brief: ClientBrief, target: str = "product") -> str:
        """Generate UX pack for operator (this app) or product (user's product). Uses decisions for product; operator is app-specific. One retry; concrete fallback."""
        decisions = self.extract_positioning_decisions(brief) if target == "product" else {}

        def _valid(out: Optional[str]) -> bool:
            if not out:
                return False
            normalized = _normalize_ux_output(out)
            return _validate_ux_output(normalized, target=target)

        if target == "operator":
            system = (
                "You are a UX writer for a CLI tool that: lets users create/save a brief, extracts positioning decisions, "
                "generates landing/linkedin/ux outputs, and saves latest/versioned files. "
                "First line of UX CONTEXT must be exactly: TARGET: operator "
                "Output ONLY the document. No preamble like 'Here is...'. No markdown bold on headers. No placeholders like [Insert...]. "
                "Use exact headers in this order: UX CONTEXT, ONBOARDING (exactly 3 items numbered 1-3), EMPTY STATE (3), ERROR (3), TOAST (3), BUTTON LABELS (8 numbered 1-8). "
                "UX CONTEXT must describe this tool. ONBOARDING/EMPTY STATE/ERROR/TOAST must reference: brief, decisions, generate, save, Ollama not running, brief.json invalid, output failed validation. "
                "BUTTON LABELS must be real actions: e.g. Review decisions, Generate landing, Save brief, Regenerate, Open latest. "
                "Banned: streamline, high-quality, unlock, revolutionize, killer app, you know the drill, meh."
            )
            user = (
                "Write a UX writing pack for THIS application (positioning operator CLI). "
                "Flows: create/save brief, extract positioning decisions, generate landing/linkedin/ux, save latest and versioned files. "
                "Errors: Ollama not running, brief.json invalid, output failed validation. "
                "Tone: clear and direct. Output only the document with exact headers and counts."
            )
        else:
            tone_instruction = (brief.tone or "Clear and friendly").strip()
            icp = decisions.get("icp") or brief.audience or "users"
            primary_problem = decisions.get("primary_problem") or brief.pain or "unclear positioning"
            desired_outcome = decisions.get("desired_outcome") or brief.offer or "clear messaging"
            differentiation = decisions.get("differentiation") or ""
            category_frame = decisions.get("category_frame") or ""
            user_parts = [
                f"Write a UX writing pack for this product: {brief.product or 'the product'}. First line of UX CONTEXT must be: TARGET: product",
                "",
                "Positioning Decisions (use these to write specific, grounded microcopy):",
                f"  ICP: {icp}",
                f"  Primary Problem: {primary_problem}",
                f"  Desired Outcome: {desired_outcome}",
            ]
            if category_frame:
                user_parts.append(f"  Category / What it is: {category_frame}")
            if differentiation:
                user_parts.append(f"  Differentiation: {differentiation}")
            user_parts += [
                "",
                f"  Product: {brief.product or 'Not specified'}",
                f"  Tone: {tone_instruction}",
            ]
            if brief.context:
                user_parts.append(f"  Context: {brief.context}")
            user_parts.append(
                "\nHARD RULES:"
                f"\nYou are a senior UX writer. Write microcopy for real users of {brief.product or 'the product'} — they are {icp}."
                f"\nTheir core problem: {primary_problem}."
                f"\nTheir desired outcome: {desired_outcome}."
                "\nCRITICAL: Do NOT copy the 'Desired Outcome', 'Differentiation', or 'Category Frame' text verbatim into your output."
                "  These are positioning reference context only. Translate them into short, specific UI microcopy."
                "  Example: 'Instead of X, users get Y' becomes a button 'Save Results' or toast 'Results ready.' — never a strategy sentence in UI."
                "\nVOCABULARY: Use vocabulary that reflects the product mechanics."
                "  Allowed nouns: messaging brain, audience, problem, positioning, landing page, ux copy, outputs, product idea, message."
                "  NEVER use generic SaaS workspace vocabulary: campaign, workflow, pipeline, project, stage, insight, ticket."
                "\nFORMAT: Each numbered item is ONE line only. No sub-descriptions, no line breaks within a numbered item."
                "\nUX CONTEXT: After 'TARGET: product', write ONE concise sentence describing the product and who uses it. "
                "  No strategy labels. No truncated decision text. Plain, product-native description only."
                "\nONBOARDING: name the actual first steps in this product — reflect the real product flow, not generic onboarding."
                "  Each step is one short sentence telling the user exactly what to do. No strategy text, no 'Instead of...' framing."
                "  Example good style: '1. Define your audience.' '2. Clarify the core problem.' '3. Generate your first output.'"
                "\nEMPTY STATE: explain what is missing at this product stage using product-native language. Guide toward the next concrete action."
                "  Keep copy short — aim for ≤ 12 words each. Name the real thing missing, not 'Add your first item'."
                "  Correct examples: 'No messaging brain yet. Describe your product to start.' / 'No landing page generated yet. Build your messaging brain first.' / 'No UX copy yet. Generate UX after defining audience and problem.'"
                "\nERROR: short, clear, actionable. Explain what failed and what to do. ≤ 15 words each."
                "  Not generic system errors. Name the product context — brain saving, generation, outputs."
                "  Correct examples: 'Could not save messaging brain. Try again.' / 'Generation failed. Refine the problem or audience.' / 'Output could not be created. Check your messaging inputs.'"
                "\nTOAST: celebrate REAL completed actions in product-specific language. ≤ 8 words each."
                "  NEVER write 'Step complete' or 'Move to the next stage'. "
                "  Confirm the specific thing the user just did."
                "  Example: 'Messaging brain saved.' or 'Audience defined.' or 'Output generated.'"
                "\nBUTTON LABELS: 1-3 words. Concrete, domain-specific. Every label must reflect an actual action in THIS product."
                "  Use a concrete verb + specific product object. All 8 must be grounded in this product's mechanics."
                "  Valid examples: 'Define Audience', 'Clarify Problem', 'Build Brain', 'Generate Landing', 'Generate UX', 'Save Brain', 'Refine Message', 'Regenerate Output'."
                "  NEVER use generic SaaS verbs: 'Launch', 'Plan', 'Review', 'Track', 'Manage', 'Add Insights', 'Get Started', 'Proceed', 'Confirm', 'Continue' alone."
                "\nDO NOT reference CLI commands, file paths (brief.json), or internal system workflows (Generate landing, Ollama, Output saved)."
                "\nBANNED phrases: something went wrong, nothing here yet, your list is empty, check your connection, desired outcome:, differentiation:, instead of generating, step complete, move to the next stage, campaign, workflow, pipeline, project, stage, insight, ticket."
                "\nExact headers: UX CONTEXT (first line TARGET: product), ONBOARDING 3, EMPTY STATE 3, ERROR 3, TOAST 3, BUTTON LABELS 8. No preamble. No markdown bold."
            )
            user = "\n".join(user_parts)
            category_qualifier = f" ({category_frame})" if category_frame else ""
            system = (
                f"You are a senior UX writer for '{brief.product or 'the product'}'{category_qualifier}, used by {icp}. "
                f"Their core problem: {primary_problem}. Their desired outcome: {desired_outcome}. "
                "First line of UX CONTEXT must be: TARGET: product. "
                "UX CONTEXT: after 'TARGET: product', write ONE plain sentence describing this product and who uses it. "
                "  No strategy labels. No truncated positioning text. Product-native description only. "
                "CRITICAL: Do NOT copy positioning context labels ('Desired Outcome:', 'Differentiation:', 'Category Frame:') or their full sentences into your output. "
                "Translate positioning context into short, specific UI microcopy. Every line must feel like it belongs in a real interface. "
                "VOCABULARY RULE: Use vocabulary that reflects the product mechanics. "
                "  Allowed nouns: messaging brain, audience, problem, positioning, landing page, ux copy, outputs, product idea, message. "
                "  NEVER use generic SaaS workspace vocabulary: campaign, workflow, pipeline, project, stage, insight, ticket. "
                "ONBOARDING: name the actual first steps users take in this product. Each step is one short sentence — what to do, not what the product is. No strategy framing. "
                "  Example style: '1. Define your audience.' '2. Clarify the problem.' '3. Generate your first output.' "
                "EMPTY STATE: name what is missing at this product stage using product-native language. Tell the user the concrete next action. ≤ 12 words per line. "
                "  Not 'Add your first item'. Name the real missing thing. "
                "  Examples: 'No messaging brain yet. Describe your product to start.' / 'No landing page generated yet. Build your messaging brain first.' / 'No UX copy yet. Generate UX after defining audience and problem.' "
                "ERROR: ≤ 15 words each. Short, clear, product-specific. Name the failure and the fix. "
                "  Not generic system messages. "
                "  Examples: 'Could not save messaging brain. Try again.' / 'Generation failed. Refine the problem or audience.' / 'Output could not be created. Check your messaging inputs.' "
                "TOAST: ≤ 8 words. Confirm the SPECIFIC action just completed. NEVER write 'Step complete' or 'Move to the next stage'. "
                "  Product-specific milestone language only. Examples: 'Messaging brain saved.' / 'Output generated.' / 'Audience defined.' "
                "BUTTON LABELS: 1-3 words. Domain-specific action verbs grounded in this product's mechanics. "
                "  Valid examples: 'Define Audience', 'Clarify Problem', 'Build Brain', 'Generate Landing', 'Generate UX', 'Save Brain', 'Refine Message', 'Regenerate Output'. "
                "  NEVER use generic SaaS verbs alone: 'Launch', 'Plan', 'Review', 'Track', 'Manage', 'Add Insights', 'Get Started', 'Begin', 'Proceed', 'Confirm', 'Continue'. "
                "DO NOT mention CLI commands, file paths (brief.json), or operator workflows. "
                "BANNED: something went wrong, nothing here yet, your list is empty, check your connection, desired outcome:, differentiation:, instead of generating, step complete, move to the next stage, campaign, workflow, pipeline, project, stage, insight, ticket, book a short working session. "
                "Exact headers: UX CONTEXT, ONBOARDING (3), EMPTY STATE (3), ERROR (3), TOAST (3), BUTTON LABELS (8). Numbered 1-N. No preamble. No bold."
            )

        if target == "product":
            icp_strict = decisions.get("icp") or brief.audience or "users"
            problem_strict = decisions.get("primary_problem") or brief.pain or "unclear positioning"
            outcome_strict = decisions.get("desired_outcome") or brief.offer or "their goal"
            category_strict = decisions.get("category_frame") or ""
            category_qualifier_strict = f" ({category_strict})" if category_strict else ""
            system_strict = (
                f"Senior UX writer for '{brief.product or 'the product'}'{category_qualifier_strict}, used by {icp_strict}. "
                f"Core problem: {problem_strict}. Desired outcome: {outcome_strict}. "
                "First line of UX CONTEXT: TARGET: product. "
                "UX CONTEXT: one plain sentence after TARGET: product — product description in user terms, no strategy labels. "
                "CRITICAL: Do NOT copy 'Desired Outcome:', 'Differentiation:', or 'Category Frame:' text into your output. Context only. "
                "Every line must be real UI microcopy — no strategy sentences, no positioning prose. "
                "VOCABULARY: Use product-native nouns only — messaging brain, audience, problem, positioning, landing page, ux copy, outputs, message. "
                "NEVER use: campaign, workflow, pipeline, project, stage, insight, ticket. "
                "ONBOARDING: actual product steps, concrete objects, one sentence each. "
                "  Example: '1. Define your audience.' '2. Clarify the problem.' '3. Generate your first output.' "
                "EMPTY STATE: ≤ 12 words. Name what is missing in product terms. Tell the user the next action. "
                "  Example: 'No messaging brain yet. Describe your product to start.' "
                "ERROR: ≤ 15 words. Name the failure and the fix in product terms. Not generic system errors. "
                "  Example: 'Could not save messaging brain. Try again.' "
                "TOAST: ≤ 8 words. Specific completed action — NEVER 'Step complete' or 'Move to the next stage'. "
                "  Example: 'Messaging brain saved.' / 'Output generated.' "
                "BUTTON LABELS: 1-3 words. Product-specific. "
                "  Valid: 'Define Audience', 'Clarify Problem', 'Build Brain', 'Generate Landing', 'Generate UX', 'Save Brain', 'Refine Message', 'Regenerate Output'. "
                "  Never 'Begin', 'Proceed', 'Confirm', 'Get Started', 'Launch', 'Plan', 'Track', 'Add Insights' alone. "
                "DO NOT mention CLI commands, file paths (brief.json), or tool-specific workflows. "
                "BANNED: something went wrong, nothing here yet, your list is empty, check your connection, desired outcome:, differentiation:, instead of generating, step complete, move to the next stage, campaign, workflow, pipeline, project, stage, insight, ticket. "
                "Exact headers and counts. No preamble. No bold."
            )
        else:
            system_strict = (
                "UX writer. Output ONLY the document. No preamble. No markdown. No placeholders. "
                "Exact headers: UX CONTEXT, ONBOARDING, EMPTY STATE, ERROR, TOAST, BUTTON LABELS. "
                "ONBOARDING 3 numbered. EMPTY STATE 3. ERROR 3. TOAST 3. BUTTON LABELS 8 numbered. "
                "Banned: streamline, high-quality, unlock, revolutionize, killer app, you know the drill, meh, [insert, [add."
            )

        try:
            out = llm_generate(system=system, user=user, model="llama3:8b", temperature=0.3)
            normalized = _normalize_ux_output(out or "")
            if target == "product":
                normalized = _ux_domain_drift_cleanup(normalized)
            if _validate_ux_output(normalized, target):
                return (normalized.rstrip("\n") + "\n")
            out = llm_generate(system=system_strict, user=user, model="llama3:8b", temperature=0.2)
            normalized = _normalize_ux_output(out or "")
            if target == "product":
                normalized = _ux_domain_drift_cleanup(normalized)
            if _validate_ux_output(normalized, target):
                return (normalized.rstrip("\n") + "\n")
        except Exception:
            pass
        return self._write_ux_pack_fallback(brief, target=target, decisions=decisions)

    def _write_ux_pack_fallback(self, brief: ClientBrief, target: str = "product", decisions: Optional[dict] = None) -> str:
        """Concrete fallback: no placeholders. Operator = this app; product = from brief."""
        decisions = decisions or {}
        if target == "operator":
            return self._ux_pack_fallback_operator()
        return self._ux_pack_fallback_product(brief, decisions)

    def _ux_pack_fallback_operator(self) -> str:
        """Concrete UX pack for this tool (brief, decisions, generate, save, errors)."""
        body = """UX CONTEXT
TARGET: operator
CLI tool: you add a client brief, extract positioning decisions, then generate landing, LinkedIn, or UX outputs. Files are saved as versioned and latest in the client outputs folder.

ONBOARDING
1. Add your client name and path to the brief, or use the demo client.
2. Run positioning to extract decisions, then run landing, linkedin, or ux_operator/ux_product.
3. Check the outputs folder for the latest file and versioned history.

EMPTY STATE
1. No brief found. Create clients/<name>/brief.json or pass --brief path.
2. No outputs yet. Run a mode (e.g. landing or linkedin) to generate the first file.
3. No decisions yet. Run positioning first if you use decision-driven modes.

ERROR
1. Ollama not running. Start Ollama and ensure the model is available.
2. brief.json invalid. Fix the JSON in the client brief file and try again.
3. Output failed validation. The run was replaced by a fallback; check the latest file.

TOAST
1. Brief saved. You can run positioning or generate next.
2. Output saved. Versioned and latest files updated.
3. Manifest appended. This run is logged in _manifest.jsonl.

BUTTON LABELS
1. Save brief
2. Review decisions
3. Generate landing
4. Generate LinkedIn
5. Generate UX pack
6. Regenerate
7. Open latest
8. Back
"""
        return (body.rstrip("\n") + "\n")

    def _ux_pack_fallback_product(self, brief: ClientBrief, decisions: dict) -> str:
        """Product UX fallback: grounded in the actual product and ICP, no operator/CLI terms.

        Uses category_frame keywords to infer realistic product mechanics for onboarding,
        empty states, toasts, and button labels. Never pastes raw strategy text into UI copy.
        """
        def _safe(s: str, default: str) -> str:
            if not s:
                return default
            if any(b in s.lower() for b in _UX_PRODUCT_OPERATOR_TERMS):
                return default
            return s.strip()

        def _short_copy(text: str, max_len: int = 55) -> str:
            """Shorten strategy text to a length safe for UI copy.

            Cuts at first sentence boundary, then word boundary if still long.
            Never returns raw multi-sentence strategy prose.
            """
            s = (text or "").strip().rstrip(".")
            for sep in [". ", "— ", " — "]:
                if sep in s:
                    s = s.split(sep)[0].strip().rstrip(".")
            if len(s) > max_len:
                s = s[:max_len].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
            return s

        product = _safe(brief.product or "", "this product")
        icp = _safe(decisions.get("icp") or brief.audience or "", "users").lower().rstrip(".")
        problem = _safe(decisions.get("primary_problem") or brief.pain or "", "the core challenge")
        outcome = _safe(decisions.get("desired_outcome") or brief.offer or "", "the desired result")
        category = _safe(decisions.get("category_frame") or "", "")

        # Use the last noun-like word of the ICP for compact references.
        # "early-stage founders" → "founders", "solo builders" → "builders", "users" → "users"
        icp_words = icp.split()
        icp_noun = icp_words[-1].capitalize() if icp_words else "User"

        # Safe short versions for use in UI copy — no multi-sentence strategy prose
        problem_copy = _short_copy(problem, 65)
        outcome_copy = _short_copy(outcome, 55)

        # Derive onboarding steps and labels from category keywords, so they feel product-specific
        cat_lower = category.lower()
        if any(w in cat_lower for w in ("messaging", "positioning", "copy", "content", "launch")):
            ob1 = f"Define who {product} is for and the problem it solves"
            ob2 = f"Shape your core message — the angle that makes {product} different"
            ob3 = "Generate your first piece and adjust from the result"
            es1 = f"No audience defined yet. Start by telling {product} who you're building for."
            es2 = "No message saved yet. Complete setup to shape your positioning."
            es3 = "No output yet. Finish setup and generate your first piece."
            t3 = "Messaging brain saved."
            labels = [
                "Define Audience", "Shape Message", "Generate Content",
                "Edit Positioning", "Save Progress", "Try Again", "See History", "Get Help",
            ]
        elif any(w in cat_lower for w in ("invest", "finance", "sip", "risk", "kyc", "wealth", "fintech")):
            ob1 = "Answer a few questions to understand your financial situation"
            ob2 = f"Complete your verification so {product} can personalise your plan"
            ob3 = "Start your first investment and track your progress"
            es1 = "No risk profile yet. Complete the questionnaire to get started."
            es2 = "No investments set up yet. Finish setup to see your plan."
            es3 = "No transactions yet. Make your first investment to see activity."
            t3 = "Profile complete. Your plan is ready."
            labels = [
                "Learn My Risk", "Complete KYC", "Start My SIP", "View Portfolio",
                "Update Profile", "Try Again", "See History", "Get Help",
            ]
        elif any(w in cat_lower for w in ("influencer", "creator", "match", "brand")):
            ob1 = "Define your brand goal and the audience you want to reach"
            ob2 = "Review creator matches based on your product brief"
            ob3 = "Approve your first creator and go live"
            es1 = "No brand brief yet. Define your goal to see creator matches."
            es2 = "No creators matched yet. Complete your brief to see results."
            es3 = "No creators live yet. Approve a creator to get started."
            t3 = "Creator approved. You are live."
            labels = [
                "Define Brand", "Review Matches", "Approve Creator", "Edit Brief",
                "Save Progress", "Try Again", "See History", "Get Help",
            ]
        else:
            ob1 = f"Tell {product} about your situation — this shapes everything that follows"
            ob2 = f"Complete your {icp_noun.lower()} profile so {product} can tailor its output"
            ob3 = f"Review your first result and refine as you go"
            es1 = f"No {icp_noun.lower()} profile yet. Finish setup to see your results."
            es2 = "This section is empty — complete the previous step to continue."
            es3 = "Nothing here. Come back once you have completed the setup."
            t3 = f"{icp_noun} profile saved."
            labels = [
                "Complete Setup", "View My Results", "Edit Profile", "Save Progress",
                "Start Over", "Try Again", "See History", "Get Help",
            ]

        body = f"""UX CONTEXT
TARGET: product
{product} for {icp}. Core problem: {problem_copy}. Goal: {outcome_copy}.

ONBOARDING
1. {ob1}.
2. {ob2}.
3. {ob3}.

EMPTY STATE
1. {es1}
2. {es2}
3. {es3}

ERROR
1. That did not save. Check your input and try again.
2. That step did not complete. Make sure all required fields are filled in.
3. This action failed. Reload and try again, or contact support if it continues.

TOAST
1. Saved. Your progress is recorded.
2. Done. Continue when you are ready.
3. {t3}

BUTTON LABELS
1. {labels[0]}
2. {labels[1]}
3. {labels[2]}
4. {labels[3]}
5. {labels[4]}
6. {labels[5]}
7. {labels[6]}
8. {labels[7]}
"""
        return (body.rstrip("\n") + "\n")


@dataclass
class CriticAgent:
    name: str = "CriticAgent"

    def review_landing_page(self, draft: str, brief: ClientBrief) -> dict:
        """Rule-based critique for writing quality and conversion clarity."""
        text = (draft or "").strip()

        flags = {
            "generic_headline": False,
            "weak_cta": False,
            "missing_audience": False,
            "missing_pain": False,
        }
        notes: list[str] = []

        # Heuristics
        generic_phrases = [
            "messaging that actually converts",
            "just like every other tool",
            "sharp, specific language",
        ]

        # Headline quality
        if "HEADLINE" in text and any(p in text for p in generic_phrases):
            flags["generic_headline"] = True
            notes.append("Headline feels generic. Prefer a concrete outcome or your specific offer.")

        # Audience presence
        audience = clean_phrase(brief.audience)
        if audience and audience.lower() not in text.lower():
            flags["missing_audience"] = True
            notes.append("Audience is not explicit enough. Name who this is for in the hero.")

        # Pain presence
        pain = clean_phrase(brief.pain)
        if pain and pain.lower()[:25] not in text.lower():
            flags["missing_pain"] = True
            notes.append("Pain is not specific. Tie the hero and problem section to the provided pain.")

        # CTA strength
        cta = clean_phrase(brief.cta)
        if cta:
            weak_words = ["start", "learn", "explore", "see", "discover"]
            if any(w in cta.lower().split()[:2] for w in weak_words):
                flags["weak_cta"] = True
                notes.append("CTA is soft. Use a concrete action: 'Get a teardown', 'Book a working session', etc.")

        # Score: start at 10 and subtract for flags
        score = 10
        score -= 2 if flags["generic_headline"] else 0
        score -= 2 if flags["missing_audience"] else 0
        score -= 2 if flags["missing_pain"] else 0
        score -= 1 if flags["weak_cta"] else 0
        score = max(1, score)

        return {
            "score": score,
            "flags": flags,
            "notes": notes,
            # main.py can toggle this to include critique in output
            "include_in_output": False,
        }


@dataclass
class GroundingAgent:
    """Verifies that LLM-extracted decisions are semantically grounded in the source brief.

    Uses token-level Jaccard overlap (stdlib only). If a decision field has no token
    overlap with its corresponding brief field, it is patched back to the brief value.
    """

    name: str = "GroundingAgent"
    threshold: float = 0.05  # minimum Jaccard overlap before patching

    def _jaccard(self, a: str, b: str) -> float:
        ta = set(re.sub(r"[^\w\s]", "", (a or "").lower()).split())
        tb = set(re.sub(r"[^\w\s]", "", (b or "").lower()).split())
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / len(ta | tb)

    def ground(self, decisions: dict, brief: ClientBrief) -> tuple[dict, list[str]]:
        """Patch decisions that have drifted from brief fields. Returns (patched, notes)."""
        patched = dict(decisions)
        notes: list[str] = []

        icp = patched.get("icp", "")
        if self._jaccard(icp, brief.audience or "") < self.threshold:
            patched["icp"] = clean_phrase(brief.audience) or icp
            notes.append("icp: low overlap with brief.audience — patched")

        problem = patched.get("primary_problem", "")
        if self._jaccard(problem, brief.pain or "") < self.threshold:
            patched["primary_problem"] = clean_sentence(brief.pain or problem)
            notes.append("primary_problem: low overlap with brief.pain — patched")

        return patched, notes


@dataclass
class FactGuardAgent:
    """Strips numeric claims not grounded in the source brief (brief.examples / brief.context).

    Percentage claims (73%) and dollar figures ($1M) that appear verbatim in neither
    brief.examples nor brief.context are replaced with [VERIFY: <claim>] markers.
    """

    name: str = "FactGuardAgent"

    def clean(self, text: str, brief: ClientBrief) -> str:
        sources = " ".join(
            filter(None, [(brief.examples or ""), (brief.context or "")])
        ).lower()

        def _guard(m: re.Match) -> str:
            claim = m.group(0)
            if claim.lower() in sources:
                return claim
            return f"[VERIFY: {claim}]"

        text = re.sub(r"\b\d[\d,]*(?:\.\d+)?%", _guard, text)
        text = re.sub(r"(?<!\w)\$[\d,]+(?:\.\d+)?[MKBmkb]?\b", _guard, text)
        return text


@dataclass
class StrategistAgent:
    """Strategy layer suggesting positioning and copy tweaks."""

    name: str = "StrategistAgent"

    def suggest(self, brief: ClientBrief, draft: str, critique: Optional[dict] = None) -> dict:
        text = (draft or "").lower()
        positioning: list[str] = []
        clarity_fixes: list[str] = []
        cta_improvements: list[str] = []
        must_include: list[str] = []

        audience = clean_phrase(brief.audience) or "your ideal customers"
        offer = clean_phrase(brief.offer) or "the core outcome the user needs"
        pain = clean_phrase(brief.pain) or "the core problem the user faces"

        if audience not in text:
            positioning.append(f"Name the audience explicitly in the hero: '{audience}'.")

        if pain[:25].lower() not in text:
            clarity_fixes.append(f"Tie the problem section directly to this pain: '{pain}'.")

        if "outcome" not in text and "results" not in text:
            positioning.append("Add one concrete outcome (metric, saved time, or clear before/after).")

        cta_text = (brief.cta or "").lower()
        if not any(w in cta_text for w in ("get", "start", "try", "request", "book", "join", "apply")):
            cta_improvements.append(
                "Use a concrete CTA with a strong action verb tied to the product's desired outcome."
            )

        must_include.append(f"Audience: {audience}")
        must_include.append(f"Offer: {offer}")

        return {
            "positioning": positioning,
            "clarity_fixes": clarity_fixes,
            "cta_improvements": cta_improvements,
            "must_include": must_include,
        }
