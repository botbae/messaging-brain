import json
import os
from dataclasses import dataclass
from typing import Callable, List, Optional

from core.llm import generate as llm_generate
from core.utils import clean_phrase, clean_sentence, lower_first


def _contains_banned_phrases(text: str, banned_list: tuple[str, ...]) -> bool:
    lower = (text or "").lower()
    return any(phrase in lower for phrase in banned_list)


def _validate_headers(text: str, required_headers: tuple[str, ...]) -> bool:
    t = (text or "").strip()
    return all(h in t for h in required_headers)


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
            "You are a B2B landing page strategist. Use ONLY the positioning decisions provided. "
            "No hype. No generic SaaS clichés. No questions in the HEADLINE. "
            "Output must use EXACT headers in this order: HEADLINE, SUBHEAD, WHO ITS FOR, PROBLEM, "
            "WHY CURRENT OPTIONS FAIL, WHAT THIS IS, DIFFERENTIATION, PROOF / SIGNALS, CTA. "
            "One block of content under each. No preamble. Banned: streamline, empower, unlock, "
            "innovative, cutting-edge, revolutionize, best-in-class, game-changing."
        )
        system_strict = (
            "B2B landing page. STRICT: Only these headers in order: HEADLINE, SUBHEAD, WHO ITS FOR, "
            "PROBLEM, WHY CURRENT OPTIONS FAIL, WHAT THIS IS, DIFFERENTIATION, PROOF / SIGNALS, CTA. "
            "HEADLINE must be a statement, not a question. No hype words. No banned phrases. Output only the document."
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
            f"User custom instructions (tone): {brief.tone or 'Clear and direct'}",
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
            return out.rstrip() + "\n"
        return self._write_landing_page_fallback(brief, decisions)

    def _write_landing_page_fallback(self, brief: ClientBrief, decisions: dict) -> str:
        """Rule-based landing template with new headers when LLM invalid or unavailable."""
        icp = decisions.get("icp", "") or clean_phrase(brief.audience) or "Your ideal customers"
        problem = decisions.get("primary_problem", "") or clean_sentence(brief.pain or "Core problem not articulated.")
        alternative = decisions.get("current_alternative", "") or "Generic options that do not address this."
        outcome = decisions.get("desired_outcome", "") or "Clear messaging that converts."
        category = decisions.get("category_frame", "") or f"{clean_phrase(brief.product) or 'Product'} for {icp}."
        diff = decisions.get("differentiation", "") or clean_phrase(brief.offer) or "Focused on this outcome."
        product = clean_phrase(brief.product) or "This product"
        tone = (brief.tone or "Clear and direct").strip()
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
[Add logos, metrics, or social proof.]

CTA
Book a short working session to sharpen your messaging.
"""
        return body.rstrip() + "\n"

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
            return out.rstrip() + "\n"

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

        return "\n".join(out_lines).rstrip() + ("\n" if draft.endswith("\n") else "\n")

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
        return body.rstrip() + "\n"

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
        return body.rstrip() + "\n"

    def rewrite_launch_pack(self, brief: ClientBrief, draft: str, strategy: dict) -> str:
        """Rule-based pass: keep structure and headers; no reorder."""
        if not draft or not strategy:
            return draft
        return draft

    def extract_positioning_decisions(self, brief: ClientBrief) -> dict:
        """Decision phase: extract positioning decisions as strict JSON; fallback to brief-derived dict if invalid."""
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
            combined = " ".join(str(data.get(k, "")) for k in _DECISION_KEYS)
            if _contains_banned_phrases(combined, _BANNED):
                return None
            return {k: (data[k] or "").strip() for k in _DECISION_KEYS}

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
        """Generate positioning doc via Ollama; fall back to minimal template if LLM unavailable."""
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
            "Write a positioning document using this brief.",
            f"Product: {brief.product or 'Not specified'}",
            f"Audience: {brief.audience or 'Not specified'}",
            f"Pain: {brief.pain or 'Not specified'}",
            f"Offer: {brief.offer or 'Not specified'}",
            f"Tone: {brief.tone or 'Clear and confident'}",
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
                return out.rstrip() + "\n"
        except Exception:
            pass
        return self._write_positioning_fallback(brief)

    def _write_positioning_fallback(self, brief: ClientBrief) -> str:
        """Minimal positioning template when Ollama is unavailable."""
        product = clean_phrase(brief.product) or "Product"
        audience = clean_phrase(brief.audience) or "Target audience"
        pain = clean_sentence(brief.pain or "Core problem not yet articulated.")
        offer = clean_phrase(brief.offer) or "Clear value proposition"
        body = f"""ICP
{audience}

CORE PAIN
{pain}

DESIRED OUTCOME
Clear messaging and positioning that converts.

UNIQUE MECHANISM
{offer}

CATEGORY FRAME
{product} sits in the space of [category]. It is for {audience} who need [outcome].

DIFFERENTIATION
Focused on [specific outcome]. Not a generic tool.

POSITIONING STATEMENT
For {audience} who {pain}, {product} is the [category] that [unique mechanism]. Unlike [alternatives], we [differentiator].

RISKS / WEAKNESS
[Add honest constraints or positioning risks.]
"""
        return body.rstrip() + "\n"

    def write_ux_pack(self, brief: ClientBrief) -> str:
        """Generate UX writing pack from positioning decisions via Ollama; fallback to template if invalid."""
        decisions = self.extract_positioning_decisions(brief)

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
        )

        def _valid(out: str) -> bool:
            return (
                bool(out)
                and _validate_headers(out, _UX_HEADERS)
                and not _contains_banned_phrases(out, _UX_BANNED)
            )

        system = (
            "You are a UX writer. Produce a UX writing pack with exact section headers in this order: "
            "UX CONTEXT, ONBOARDING (exactly 3 options), EMPTY STATE (3 options), ERROR (3 options), "
            "TOAST (3 options), BUTTON LABELS (8 options). "
            "Use clear, concise language. No filler or buzzwords. Output only the document with those headers."
        )
        system_strict = (
            "You are a UX writer. Strict rules: Use ONLY these exact headers in this order: "
            "UX CONTEXT, ONBOARDING, EMPTY STATE, ERROR, TOAST, BUTTON LABELS. "
            "Under ONBOARDING exactly 3 options. Under EMPTY STATE exactly 3. Under ERROR exactly 3. "
            "Under TOAST exactly 3. Under BUTTON LABELS exactly 8 options. "
            "Banned: streamline, high-quality, unlock, revolutionize, killer app, you know the drill, meh. "
            "Plain language only. Output only the document. No preamble."
        )
        tone_instruction = (brief.tone or "Clear and friendly").strip()
        user_parts = [
            "Write a UX writing pack using ONLY the positioning decisions below.",
            "",
            "Positioning Decisions:",
            f"  ICP: {decisions.get('icp', '')}",
            f"  Primary Problem: {decisions.get('primary_problem', '')}",
            f"  Current Alternative: {decisions.get('current_alternative', '')}",
            f"  Desired Outcome: {decisions.get('desired_outcome', '')}",
            f"  Category Frame: {decisions.get('category_frame', '')}",
            f"  Differentiation: {decisions.get('differentiation', '')}",
            "",
            f"User custom instructions (tone): {tone_instruction}",
            "",
            "Instructions: Microcopy must be specific to the ICP and primary_problem. "
            "Frame current_alternative and why it fails as friction. Target desired_outcome as the behavior we want. "
            "Keep UX CONTEXT, ONBOARDING (3), EMPTY STATE (3), ERROR (3), TOAST (3), BUTTON LABELS (8).",
            "",
            "Output format (exact headers in this order): UX CONTEXT, ONBOARDING, EMPTY STATE, ERROR, TOAST, BUTTON LABELS.",
        ]
        user = "\n".join(user_parts)

        out = _run_with_retry(
            generate_fn=lambda: llm_generate(system=system, user=user, model="llama3:8b", temperature=0.3),
            strict_generate_fn=lambda: llm_generate(system=system_strict, user=user, model="llama3:8b", temperature=0.25),
            validator_fn=_valid,
        )
        if out:
            return out.rstrip() + "\n"
        return self._write_ux_pack_fallback(brief, decisions)

    def _write_ux_pack_fallback(self, brief: ClientBrief, decisions: dict) -> str:
        """Minimal UX pack template when LLM unavailable or validation fails."""
        icp = decisions.get("icp", "") or clean_phrase(brief.audience) or "your users"
        problem = decisions.get("primary_problem", "") or "Get to the outcome faster."
        outcome = decisions.get("desired_outcome", "") or "Clear next step."
        product = clean_phrase(brief.product) or "Product"
        tone = lower_first(clean_phrase(brief.tone) or "clear and friendly")
        body = f"""UX CONTEXT
{product} for {icp}. {problem} Tone: {tone}. Target behavior: {outcome}.

ONBOARDING
1. Welcome. Get started in a few steps.
2. First time here? Set up your first item.
3. Let's get you started.

EMPTY STATE
1. Nothing here yet. Add your first item.
2. Your list is empty. Create something to get started.
3. No items yet. Add one to begin.

ERROR
1. Something went wrong. Try again in a moment.
2. We couldn't complete that. Check your connection and retry.
3. Action failed. If it keeps happening, contact support.

TOAST
1. Saved. Your changes are stored.
2. Done. You can keep editing or leave.
3. Updated. Refresh to see changes.

BUTTON LABELS
1. Save
2. Cancel
3. Continue
4. Back
5. Submit
6. Edit
7. Delete
8. Done
"""
        return body.rstrip() + "\n"


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
