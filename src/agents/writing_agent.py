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
)
_UX_PLACEHOLDER_SUBSTRINGS = ("[insert", "[add", "insert context", "[context", "[product")

_UX_PRODUCT_BANNED = (
    "welcome", "get started", "first time", "add your first", "nothing here yet",
    "your list is empty", "something went wrong", "try again", "check your connection",
    "done", "updated", "saved", "continue", "submit",
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
        t = t.replace(f"**{h}**", h)
    lines = t.splitlines()
    out = []
    for line in lines:
        s = line.strip()
        if s.upper() == "UX WRITING PACK" or (s.startswith("**") and s.endswith("**") and "UX WRITING PACK" in s.upper()):
            continue
        out.append(line)
    return "\n".join(out).strip()


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

    if target == "product":
        if _contains_banned_phrases(text, _UX_PRODUCT_BANNED):
            return False
        if _contains_banned_phrases(t, _UX_PRODUCT_OPERATOR_TERMS):
            return False
        if "TARGET: product" not in text and "target: product" not in t:
            return False
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
            numbered = [x.strip() for x in block.splitlines() if x.strip() and x.strip()[0].isdigit()]
            tags_in_section = set()
            for line in numbered:
                after_num = line.lstrip("0123456789").lstrip(".) ")
                after_num_lower = after_num.lower()
                if not any(after_num_lower.startswith(tag.lower()) for tag in _UX_PRODUCT_SCENARIO_TAGS):
                    return False
                for tag in _UX_PRODUCT_SCENARIO_TAGS:
                    if tag.lower() in after_num_lower:
                        tags_in_section.add(tag.lower())
            if len(tags_in_section) < 2:
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
    required_headers = (
        "ICP", "CORE PAIN", "DESIRED OUTCOME", "UNIQUE MECHANISM",
        "CATEGORY FRAME", "DIFFERENTIATION", "POSITIONING STATEMENT", "RISKS / WEAKNESS",
    )
    for h in required_headers:
        if h not in t:
            score -= 1.5
            notes.append(f"Missing section: {h}")
    if len(t) < 200:
        score -= 1.0
        notes.append("Output is very short; consider more detail.")
    if len(t) > 3000:
        score -= 0.5
        notes.append("Output is long; consider tightening.")
    buzz = ["revolutionize", "game-changer", "disrupt", "best-in-class"]
    for b in buzz:
        if b in t.lower():
            score -= 0.5
            notes.append(f"Avoid buzzword: '{b}'")
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
        )

        def _headline_has_question(text: str) -> bool:
            t = (text or "").strip()
            if "HEADLINE" not in t:
                return False
            idx = t.find("HEADLINE")
            end = t.find("\n\n", idx) if idx >= 0 else -1
            block = t[idx : end if end > 0 else len(t)]
            return "?" in block

        def _valid(out: str) -> bool:
            return (
                bool(out)
                and _validate_headers(out, _LANDING_HEADERS)
                and not _contains_banned_phrases(out, _LANDING_BANNED)
                and not _headline_has_question(out)
            )

        system = (
            "You are a B2B landing page strategist. Write from the positioning decisions only — no invented claims. "
            "No hype. No generic SaaS clichés. No questions in the HEADLINE. "
            "HEADLINE must name the ICP and desired_outcome in one concrete declarative statement — not a slogan. "
            "PROBLEM must state primary_problem in plain language — concrete people facing real friction, not abstract nouns. "
            "WHY CURRENT OPTIONS FAIL must explain specifically why current_alternative fails the ICP, not just that it does. "
            "DIFFERENTIATION must lead with differentiation and close with a direct contrast against anti_positioning. "
            "Do not repeat the same sentence structure across sections. "
            "Output must use EXACT headers in this order: HEADLINE, SUBHEAD, WHO ITS FOR, PROBLEM, "
            "WHY CURRENT OPTIONS FAIL, WHAT THIS IS, DIFFERENTIATION, PROOF / SIGNALS, CTA. "
            "One block of content under each. No preamble. Banned: streamline, empower, unlock, "
            "innovative, cutting-edge, revolutionize, best-in-class, game-changing."
        )
        system_strict = (
            "B2B landing page. STRICT: Only these headers in order: HEADLINE, SUBHEAD, WHO ITS FOR, "
            "PROBLEM, WHY CURRENT OPTIONS FAIL, WHAT THIS IS, DIFFERENTIATION, PROOF / SIGNALS, CTA. "
            "HEADLINE: declarative statement naming who it is for and what outcome they get. Not a question, not a slogan. "
            "PROBLEM: one or two sentences naming the real friction in concrete terms. "
            "DIFFERENTIATION: state it directly, then contrast with what this is not. "
            "No hype words. No banned phrases. Output only the document."
        )
        user_parts = [
            "Write a landing page using ONLY the positioning decisions below.",
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
            f"Tone: {brief.tone or 'Clear and direct'}",
            "",
            "Per-section instructions (do not include these in output):",
            "  HEADLINE: One declarative statement. Name the ICP and desired_outcome. No slogans, no rhetorical devices.",
            "  SUBHEAD: One sentence bridging primary_problem to desired_outcome.",
            "  WHO ITS FOR: Name the ICP directly. One or two concrete sentences about their situation.",
            "  PROBLEM: State primary_problem without abstraction. Name real friction, not categories.",
            "  WHY CURRENT OPTIONS FAIL: Explain specifically why current_alternative falls short — name the gap.",
            "  WHAT THIS IS: State category_frame plainly. Say what it is and does, not what it transforms.",
            "  DIFFERENTIATION: Lead with differentiation. Close with one contrast against anti_positioning.",
            "  PROOF / SIGNALS: One concrete signal — a specific outcome, behavior, or metric — that supports differentiation. Do not write 'To be added'.",
            "  CTA: One short action line tied to desired_outcome. Use a concrete verb.",
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
        alternative = decisions.get("current_alternative", "") or "Generic options that do not address this."
        outcome = decisions.get("desired_outcome", "") or clean_phrase(brief.offer) or "Clear messaging that converts."
        category = decisions.get("category_frame", "") or f"{clean_phrase(brief.product) or 'Product'} for {icp}."
        diff = decisions.get("differentiation", "") or clean_phrase(brief.offer) or "Focused on this outcome."
        product = clean_phrase(brief.product) or "This product"
        cta = clean_sentence(brief.cta or "Book a short working session.")
        proof = clean_phrase(brief.examples or "") or ""
        proof_block = f"From the brief: {proof}" if proof else "To be added: client logos, testimonials, or a concrete metric."
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
        """Deterministic rewrite pass based on critic feedback.

        This is intentionally rule-based (no LLM) so the system remains free and predictable.
        """
        # Rebuild key sections with slightly stronger specificity.
        product = clean_phrase(brief.product) or "Your product"
        audience = clean_phrase(brief.audience) or "your ideal customers"
        pain = clean_sentence(brief.pain or "Visitors do not quickly understand why your product matters")

        offer_phrase = lower_first(clean_phrase(brief.offer) or "a clear, conversion-focused narrative around your product")
        tone_phrase = lower_first(clean_phrase(brief.tone) or "clear, confident, and human")
        cta = clean_sentence(brief.cta or "Book a short call to sharpen your product story")

        # If the critic detected generic headline, make headline more concrete using the offer.
        headline = f"{product}: {offer_phrase}" if critique.get("flags", {}).get("generic_headline") else f"{product}: messaging that actually converts"

        # If the critic thinks CTA is weak, harden it with a more specific action.
        if critique.get("flags", {}).get("weak_cta"):
            cta = clean_sentence(brief.cta or "Get a 15-minute messaging teardown")

        # If the critic thinks the problem is generic, tie it to the user-provided pain.
        problem = (
            f"Right now, your page does not make the value obvious for {audience}. {pain} "
            "So visitors skim, feel uncertain, and bounce."
        )

        solution = (
            "We turn your brief into sharp, specific language that shows the problem, the outcome, "
            "and why your product is the obvious next step."
        )

        subhead = (
            f"For {audience}. {pain} "
            f"This positions you with {offer_phrase} in a {tone_phrase} voice."
        )

        examples_section = ""
        if brief.examples:
            examples_section = f"""
EXAMPLES / INSPIRATION
{brief.examples}
""".rstrip()

        extra_context_section = ""
        if brief.context:
            extra_context_section = f"""
ADDITIONAL CONTEXT
{brief.context}
""".rstrip()

        # Critique section (optional): include only if requested by the caller.
        critique_block = ""
        if critique.get("include_in_output"):
            critique_block = f"""
CRITIQUE (AUTO)
Score: {critique.get('score', 'NA')}/10
""".rstrip()
            notes = critique.get("notes", [])
            if notes:
                critique_block += "\n" + "\n".join([f"- {n}" for n in notes])

        body_v2 = f"""
HEADLINE
{headline}

SUBHEAD
{subhead}

PROBLEM
{problem}

SOLUTION
{solution}

CORE PROMISE
If a smart, distracted visitor only reads this page once, they will still remember what you do and why it is worth trying.

KEY SECTIONS
1. Hero: one clear promise tied to the main pain.
2. Social proof: logos, short quotes, and a simple metric if you have it.
3. Product tour: 3–5 moments that show how life feels with your product.
4. Objections: "What if this is too complex / risky / expensive?" answered in plain language.
5. Final CTA: one simple next step.

TONE & VOICE
Write in a {tone_phrase} tone. Prefer concrete examples over buzzwords. Fewer adjectives, more specifics.

CALL TO ACTION
{cta}
""".rstrip()

        # Append optional blocks
        blocks = [body_v2]
        if critique_block:
            blocks.append(critique_block)
        if examples_section:
            blocks.append(examples_section)
        if extra_context_section:
            blocks.append(extra_context_section)

        return "\n\n".join(blocks) + "\n"

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
        offer_phrase = lower_first(clean_phrase(brief.offer) or "clear messaging and positioning")

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
        offer = clean_phrase(brief.offer) or "Clear value proposition"
        return {
            "icp": audience,
            "primary_problem": pain,
            "current_alternative": "Generic tools that do not address this specifically.",
            "desired_outcome": "Clear messaging and positioning that converts.",
            "category_frame": f"{product} sits in the space of product messaging and positioning for {audience}.",
            "differentiation": f"Focused on {offer}. Not a generic tool.",
            "anti_positioning": "We are not a generic content or marketing agency.",
        }

    def write_positioning(self, brief: ClientBrief) -> str:
        """Generate positioning doc via LLM; fall back to minimal template if unavailable.

        Uses pre-extracted positioning decisions (from brain or LLM) so that the output
        reflects the Messaging Brain when product_profile.json has been loaded.
        """
        decisions = self.extract_positioning_decisions(brief)

        system = (
            "You are an industry-grade positioning strategist. "
            "Produce a clear, structured positioning document. "
            "Use concrete language. No hype or buzzwords. "
            "You must use exactly these section headers (one block of content under each): "
            "ICP, CORE PAIN, DESIRED OUTCOME, UNIQUE MECHANISM, CATEGORY FRAME, "
            "DIFFERENTIATION, POSITIONING STATEMENT, RISKS / WEAKNESS. "
            "Output only the document with those headers. No preamble."
        )
        user_parts = [
            "Write a positioning document using the brief and pre-extracted decisions below.",
            f"Product: {brief.product or 'Not specified'}",
            f"Audience: {brief.audience or 'Not specified'}",
            f"Pain: {brief.pain or 'Not specified'}",
            f"Offer: {brief.offer or 'Not specified'}",
            f"Tone: {brief.tone or 'Clear and confident'}",
            "",
            "Pre-extracted Positioning Decisions (use these to drive the document):",
            f"  ICP: {decisions.get('icp', '')}",
            f"  Primary Problem: {decisions.get('primary_problem', '')}",
            f"  Current Alternative: {decisions.get('current_alternative', '')}",
            f"  Desired Outcome: {decisions.get('desired_outcome', '')}",
            f"  Category Frame: {decisions.get('category_frame', '')}",
            f"  Differentiation: {decisions.get('differentiation', '')}",
            f"  Anti-Positioning: {decisions.get('anti_positioning', '')}",
        ]
        if brief.examples:
            user_parts.append(f"Examples: {brief.examples}")
        if brief.context:
            user_parts.append(f"Context: {brief.context}")
        user_parts.append(
            "\nOutput format (exact headers):\nICP\n\nCORE PAIN\n\nDESIRED OUTCOME\n\n"
            "UNIQUE MECHANISM\n\nCATEGORY FRAME\n\nDIFFERENTIATION\n\n"
            "POSITIONING STATEMENT\n\nRISKS / WEAKNESS"
        )
        user = "\n".join(user_parts)

        try:
            out = llm_generate(system=system, user=user, model="llama3:8b", temperature=0.3)
            if out and "ICP" in out and "POSITIONING STATEMENT" in out and "RISKS / WEAKNESS" in out:
                return (out.rstrip("\n") + "\n")
        except Exception:
            pass
        return self._write_positioning_fallback(brief)

    def _write_positioning_fallback(self, brief: ClientBrief) -> str:
        """Brief-interpolated positioning template when Ollama is unavailable."""
        product = clean_phrase(brief.product) or "Product"
        audience = clean_phrase(brief.audience) or "Target audience"
        pain_phrase = lower_first(clean_phrase(brief.pain or "articulate value clearly"))
        pain_sentence = clean_sentence(brief.pain or "Core problem not yet articulated.")
        offer = clean_phrase(brief.offer) or "a focused, high-signal alternative"
        cta = clean_phrase(brief.cta or "Book a working session")
        body = f"""ICP
{audience}

CORE PAIN
{pain_sentence}

DESIRED OUTCOME
{offer}

UNIQUE MECHANISM
Focused, done-with-you engagement from a structured brief — not a generic template or self-serve tool.

CATEGORY FRAME
{product} is a positioning and messaging tool for {audience}.

DIFFERENTIATION
{offer}. Scoped to one outcome, not a broad-purpose content platform.

POSITIONING STATEMENT
For {audience} who struggle to {pain_phrase}, {product} delivers {offer}. Unlike generic writing tools, it works from a structured brief and produces specific, grounded copy.

RISKS / WEAKNESS
Scope is limited to messaging and positioning. Requires a complete brief to produce useful output. Results depend on the quality of the input brief.
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
            user_parts = [
                f"Write a UX writing pack for this product: {brief.product or 'the product'}. First line of UX CONTEXT must be: TARGET: product",
                "",
                "Positioning Decisions (use these to write specific, grounded microcopy):",
                f"  ICP: {icp}",
                f"  Primary Problem: {primary_problem}",
                f"  Desired Outcome: {desired_outcome}",
            ]
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
                "\nHARD RULES: Every numbered microcopy line MUST begin with one of: [brief intake], [decision review], [generation review]. "
                f"These are the three workflow stages for {brief.product or 'the product'}: intake, decisions, generation. "
                f"Ground every line in the ICP ({icp}) and primary problem ({primary_problem}). "
                "Name real people and real friction — not abstract states like 'nothing here' or 'something went wrong'. "
                "Empty states must describe what is missing from the user's actual workflow at that stage. "
                "Error messages must explain what failed in product terms, not system terms. "
                "Button labels must reflect concrete actions in the three workflow stages. "
                "DO NOT reference CLI commands, file paths (brief.json), or operator workflows (Generate landing, Ollama, Output saved). "
                "BANNED phrases: welcome, get started, first time, add your first, nothing here yet, your list is empty, "
                "something went wrong, try again, check your connection, done, updated, saved, continue, submit. "
                "Exact headers: UX CONTEXT (first line TARGET: product), ONBOARDING 3, EMPTY STATE 3, ERROR 3, TOAST 3, BUTTON LABELS 8. No preamble. No markdown bold."
            )
            user = "\n".join(user_parts)
            system = (
                f"You are a UX writer for '{brief.product or 'the product'}', used by {icp}. "
                f"Their core problem: {primary_problem}. Their desired outcome: {desired_outcome}. "
                "First line of UX CONTEXT must be: TARGET: product. "
                "Every numbered line MUST start with one of: [brief intake], [decision review], [generation review]. "
                "These tags mark the three stages of this product's workflow — intake, decisions, generation. "
                "Ground all copy in the ICP's real context and specific problem. "
                "Empty states must name what is absent at that workflow stage, not generic emptiness. "
                "Errors must describe what went wrong in product terms. "
                "DO NOT mention CLI commands, file paths (brief.json), or tool-specific operator workflows. "
                "BANNED: welcome, get started, first time, add your first, nothing here yet, your list is empty, "
                "something went wrong, try again, check your connection, done, updated, saved, continue, submit. "
                "Exact headers: UX CONTEXT, ONBOARDING (3), EMPTY STATE (3), ERROR (3), TOAST (3), BUTTON LABELS (8). Numbered 1-N. No preamble. No bold."
            )

        if target == "product":
            icp_strict = decisions.get("icp") or brief.audience or "users"
            problem_strict = decisions.get("primary_problem") or brief.pain or "unclear positioning"
            system_strict = (
                f"UX writer for '{brief.product or 'the product'}', used by {icp_strict}. "
                f"Core problem: {problem_strict}. "
                "First line of UX CONTEXT: TARGET: product. "
                "Every numbered line MUST start with [brief intake], [decision review], or [generation review]. "
                "Ground all copy in the ICP's real context — no generic states, no system-speak. "
                "DO NOT mention CLI commands, file paths (brief.json), or tool-specific workflows (Generate landing, Ollama, Output saved). "
                "BANNED: welcome, get started, first time, add your first, nothing here yet, your list is empty, something went wrong, try again, check your connection, done, updated, saved, continue, submit. "
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
            if _validate_ux_output(normalized, target):
                return (normalized.rstrip("\n") + "\n")
            out = llm_generate(system=system_strict, user=user, model="llama3:8b", temperature=0.2)
            normalized = _normalize_ux_output(out or "")
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
        """Concrete UX pack for product mode: scenario tags, no operator/CLI terms, no banned phrases."""
        def _safe(s: str, default: str) -> str:
            if not s:
                return default
            lower = s.lower()
            if any(b in lower for b in _UX_PRODUCT_BANNED):
                return default
            if any(b in lower for b in _UX_PRODUCT_OPERATOR_TERMS):
                return default
            return s.strip()
        product = _safe(brief.product or "", "the product")
        icp = _safe(decisions.get("icp") or brief.audience or "", "your team")
        problem = _safe(decisions.get("primary_problem") or brief.pain or "", "unclear positioning")
        outcome = _safe(decisions.get("desired_outcome") or "", "messaging that resonates")
        offer = _safe(brief.offer or "", "a clearer story")
        body = f"""UX CONTEXT
TARGET: product
{product} for {icp}. Core problem: {problem}. Desired outcome: {outcome}.

ONBOARDING
1. [brief intake] Paste your product notes—we'll shape them into a tight story for {icp}.
2. [decision review] Review the positioning decisions pulled from your brief.
3. [generation review] Your first draft is ready. Open it to review and request a rewrite if needed.

EMPTY STATE
1. [brief intake] No brief yet. Add your product notes to begin positioning.
2. [decision review] No positioning decisions yet. Paste your brief to extract them.
3. [generation review] No draft yet. Run positioning first, then request a draft.

ERROR
1. [brief intake] Brief is incomplete. Fill in the audience, pain, and offer fields.
2. [decision review] Positioning failed. Check that your brief has enough detail to extract decisions.
3. [generation review] Draft failed validation. Request a regeneration or adjust your brief.

TOAST
1. [brief intake] Brief captured. Positioning decisions will be extracted next.
2. [decision review] Decisions locked. Your draft will reflect {offer}.
3. [generation review] Draft ready. Review and request a rewrite or approve to finalize.

BUTTON LABELS
1. Add brief
2. Review decisions
3. Request draft
4. Rewrite draft
5. Approve draft
6. Start over
7. View history
8. Back
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
        offer = clean_phrase(brief.offer) or "clear, high-conversion messaging"
        pain = clean_phrase(brief.pain) or "struggling to explain the value clearly"

        if audience not in text:
            positioning.append(f"Name the audience explicitly in the hero: '{audience}'.")

        if pain[:25].lower() not in text:
            clarity_fixes.append(f"Tie the problem section directly to this pain: '{pain}'.")

        if "outcome" not in text and "results" not in text:
            positioning.append("Add one concrete outcome (metric, saved time, or clear before/after).")

        if "book" not in (brief.cta or "").lower():
            cta_improvements.append(
                "Use a concrete CTA like 'Book a 20-minute working session to sharpen your story.'"
            )

        must_include.append(f"Audience: {audience}")
        must_include.append(f"Offer: {offer}")

        return {
            "positioning": positioning,
            "clarity_fixes": clarity_fixes,
            "cta_improvements": cta_improvements,
            "must_include": must_include,
        }
