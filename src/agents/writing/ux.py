"""UX writer: UX validators, domain-drift cleanup and UXWriterMixin.

Split out of agents/writing_agent.py; import from there for a stable API.
"""

import re

from typing import Optional

from core.model_provider import generate as llm_generate
from core.utils import clean_phrase, lower_first
from agents.writing.common import (
    ClientBrief,
    _contains_banned_phrases,
    _extract_slots,
    _prep_ctx,
    _strip_product_subject,
)


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


def _clean_ux_context(text: str) -> str:
    """Clean UX CONTEXT section: remove strategy labels, 'Goal:', bloated sentences.

    UX CONTEXT after 'TARGET: product' must be one short, readable paragraph.
    """
    if not text or "UX CONTEXT" not in text:
        return text
    ctx_start = text.find("UX CONTEXT")
    # Find next header
    next_header_pos = len(text)
    for h in ("ONBOARDING", "EMPTY STATE", "ERROR", "TOAST", "BUTTON LABELS"):
        hp = text.find(h, ctx_start + 10)
        if 0 < hp < next_header_pos:
            next_header_pos = hp
    ctx_block = text[ctx_start:next_header_pos]
    ctx_lines = ctx_block.splitlines()
    cleaned_lines = []
    for line in ctx_lines:
        s = line.strip()
        # Keep header and TARGET line
        if s == "UX CONTEXT" or s.startswith("TARGET:"):
            cleaned_lines.append(line)
            continue
        # Remove strategy label prefixes
        for prefix in ("Goal:", "Core problem:", "Primary problem:", "Desired outcome:", "Category:", "Differentiation:"):
            if s.startswith(prefix):
                s = s[len(prefix):].strip()
                break
        # Remove lines that are just strategy labels
        if s.lower().startswith("to develop a clear and compelling") or s.lower().startswith("goal:"):
            continue
        if s:
            cleaned_lines.append(s)
    new_ctx = "\n".join(cleaned_lines)
    return text[:ctx_start] + new_ctx + "\n\n" + text[next_header_pos:]


def _ux_domain_drift_cleanup(text: str, product_name: str = "", category: str = "") -> str:
    """Post-generation pass: replace generic SaaS patterns with product-native equivalents.

    This is a rule-based string substitution pass — it does not call the LLM.
    It catches common domain-drift phrases that slip through the banned list check.
    Uses the actual product name and category to make replacements contextual.
    """
    if not text:
        return text

    # Determine product-native replacement nouns from category + product name
    cat_lower = (category or "").lower()
    prod_lower = (product_name or "").lower()
    _drift_haystack = f"{cat_lower} {prod_lower}"
    if any(w in _drift_haystack for w in ("messaging", "positioning", "copy", "content", "launch")):
        output_noun = "output"
        setup_noun = "messaging brain"
        action_noun = "generate"
    elif any(w in cat_lower for w in ("invest", "finance", "sip", "risk", "kyc", "wealth", "fintech")):
        output_noun = "plan"
        setup_noun = "profile"
        action_noun = "set up"
    elif any(w in cat_lower for w in ("influencer", "creator", "match", "brand")):
        output_noun = "match"
        setup_noun = "brief"
        action_noun = "find"
    elif any(w in cat_lower for w in ("sanctuary", "shelter", "animal", "care", "rescue")):
        output_noun = "record"
        setup_noun = "profile"
        action_noun = "register"
    else:
        output_noun = "result"
        setup_noun = "profile"
        action_noun = "start"

    pname = product_name or "this product"

    replacements = (
        # Campaign drift
        ("Launch Campaign", f"Create {output_noun.capitalize()}"),
        ("launch campaign", f"create {output_noun}"),
        ("Campaign failed", f"{output_noun.capitalize()} creation failed"),
        ("campaign failed", f"{output_noun} creation failed"),
        ("No campaign defined", f"No {output_noun} defined yet"),
        ("no campaign defined", f"no {output_noun} defined yet"),
        ("No campaign brief yet", f"No {setup_noun} defined yet"),
        ("no campaign brief yet", f"no {setup_noun} defined yet"),
        ("No campaigns launched yet", f"No {output_noun}s created yet"),
        ("no campaigns launched yet", f"no {output_noun}s created yet"),
        ("Campaign launched", f"{output_noun.capitalize()} created"),
        ("campaign launched", f"{output_noun} created"),
        ("Define Campaign", f"Define {setup_noun.split()[-1].capitalize()}"),
        ("define campaign", f"define {setup_noun.split()[-1]}"),
        # Insight drift
        ("Add Insights", f"Build {setup_noun.split()[-1].capitalize()}"),
        ("add insights", f"build {setup_noun.split()[-1]}"),
        ("Review Insights", f"Review {output_noun.capitalize()}"),
        ("review insights", f"review {output_noun}"),
        # Workflow / pipeline / project drift
        ("No workflow yet", f"No {setup_noun} yet"),
        ("no workflow yet", f"no {setup_noun} yet"),
        ("your pipeline", f"your {output_noun}s"),
        ("the pipeline", f"the {output_noun}s"),
        # Review Progress drift
        ("Review Progress", f"View {output_noun.capitalize()}"),
        ("review progress", f"view {output_noun}"),
        # Stage drift
        ("move to next stage", "continue"),
        ("move to the next stage", "continue"),
        ("Move to Next Stage", "Continue"),
        ("Move to the Next Stage", "Continue"),
        ("next stage", "next step"),
        ("Next Stage", "Next Step"),
        ("plan ready", f"{output_noun} ready"),
        ("Plan Ready", f"{output_noun.capitalize()} Ready"),
    )
    result = text
    for old, new in replacements:
        result = result.replace(old, new)
    return result


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
        # Reject generic shell-native button labels when target is product
        if target == "product" and bl_lines:
            _UX_BUTTON_SHELL_BANNED = (
                "complete setup", "view my results", "edit profile", "save progress",
                "start over", "try again", "see history", "get help", "update profile",
                "view results", "get started", "see results", "view history",
                "save changes", "confirm changes", "submit", "proceed",
            )
            for lbl_line in bl_lines:
                lbl = re.sub(r"^\d+\.\s*", "", lbl_line).strip().lower()
                if lbl in _UX_BUTTON_SHELL_BANNED:
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


# Internal tooling phrases that must never appear in user-facing CTAs.
# These are product-builder / admin labels that leaked into generated output.
_CTA_INTERNAL_BANNED: tuple[str, ...] = (
    "define icp",
    "review brief",
    "generate messaging",
    "generate output",
    "generate copy",
    "create brain",
    "build brain",
    "create brief",
    "review brain",
    "run brain",
    "extract decisions",
    "define audience",
    "create profile",
    "review profile",
    "set up brain",
    "configure brain",
)


def _ux_cta_ok(cta: str) -> bool:
    """Return True if a UX CTA is 2-5 words and contains no internal tooling phrases."""
    if not cta:
        return False
    words = cta.split()
    if len(words) < 2 or len(words) > 5:
        return False
    cta_lower = cta.lower()
    if any(phrase in cta_lower for phrase in _CTA_INTERNAL_BANNED):
        return False
    return True


class UXWriterMixin:
    """UX microcopy, UX pack and UX slot generation.

    Mixed into WritingAgent; methods rely on its fields (brain_decisions,
    positioning, narrative) and may call methods from the other mixins.
    """

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

    def write_ux_pack(self, brief: ClientBrief, target: str = "product") -> str:
        """Generate UX pack for operator (this app) or product (user's product). Uses positioning + narrative for product; operator is app-specific. One retry; concrete fallback."""
        decisions = self.extract_positioning_decisions(brief) if target == "product" else {}
        pos = self.positioning  # PositioningContext (may be None)
        nar = self.narrative    # NarrativeContext (may be None)

        # Check narrative readiness for product UX — if too thin, return guidance instead of bad output
        if target == "product" and nar:
            nar_filled = getattr(nar, "filled_count", lambda: 0)()
            if nar_filled < 3:
                return self._ux_not_ready_message(brief, nar_filled)

        def _valid(out: Optional[str]) -> bool:
            if not out:
                return False
            normalized = _normalize_ux_output(out)
            return _validate_ux_output(normalized, target=target)

        # Derive product-native vocabulary and button examples from category
        cat_lower = (decisions.get("category_frame", "") or "").lower() if decisions else ""
        if any(w in cat_lower for w in ("messaging", "positioning", "copy", "content", "launch")):
            vocab_nouns = "messaging brain, audience, problem, positioning, landing page, ux copy, outputs, product idea, message"
            vocab_banned = "campaign, workflow, pipeline, project, stage, insight, ticket"
            button_examples = "e.g. Build Brain, Review Positioning, Generate Landing, Generate UX, Define Audience, Save Brain"
        elif any(w in cat_lower for w in ("invest", "finance", "sip", "risk", "kyc", "wealth", "fintech")):
            vocab_nouns = "portfolio, risk profile, SIP, KYC, investment, plan, questionnaire, returns, holdings"
            vocab_banned = "campaign, workflow, pipeline, messaging brain, landing page, positioning, content"
            button_examples = "e.g. Learn My Risk, Complete KYC, Start My SIP, View Portfolio, Update Profile, See History"
        elif any(w in cat_lower for w in ("influencer", "creator", "match", "brand")):
            vocab_nouns = "brand, creator, match, brief, audience, content, collaboration, approval"
            vocab_banned = "campaign, workflow, pipeline, messaging brain, landing page, positioning, ticket"
            button_examples = "e.g. Add Brand, Find Creator, Create Match, Request Approval, View Collaboration"
        elif any(w in cat_lower for w in ("sanctuary", "shelter", "animal", "care", "rescue", "cow", "gaushala")):
            vocab_nouns = "animal, record, caretaker, health check, feeding, shelter, donation, sponsor"
            vocab_banned = "campaign, workflow, pipeline, messaging brain, landing page, positioning, ticket, SaaS"
            button_examples = "e.g. Add Animal, Log Health Check, Add Sponsor, View Care Records, Record Donation, Schedule Feeding"
        else:
            vocab_nouns = "profile, setup, result, input, output, settings, account"
            vocab_banned = "campaign, workflow, pipeline, project, stage, insight, ticket"
            button_examples = "concrete verb + product object from this domain (NOT Complete Setup, View Results, Edit Profile, Save Progress)"

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
            icp = (getattr(pos, "icp", "") if pos else "") or decisions.get("icp") or brief.audience or "users"
            primary_problem = (getattr(pos, "core_problem", "") if pos else "") or decisions.get("primary_problem") or brief.pain or "unclear positioning"
            desired_outcome = (getattr(pos, "promise", "") if pos else "") or decisions.get("desired_outcome") or brief.offer or "clear messaging"
            differentiation = (getattr(pos, "differentiation", "") if pos else "") or decisions.get("differentiation") or ""
            category_frame = (getattr(pos, "category", "") if pos else "") or decisions.get("category_frame") or ""

            # Extract narrative fields for richer UX grounding
            user_journey = getattr(nar, "user_journey", "") if nar else ""
            product_story = getattr(nar, "product_story", "") if nar else ""
            solution_story = getattr(nar, "solution_story", "") if nar else ""

            user_parts = [
                f"Write a UX writing pack for this product: {brief.product or 'the product'}. First line of UX CONTEXT must be: TARGET: product",
                "",
                "Positioning (what this product IS):",
                f"  ICP: {icp}",
                f"  Core Problem: {primary_problem}",
                f"  Promise: {desired_outcome}",
            ]
            if category_frame:
                user_parts.append(f"  Category: {category_frame}")
            if differentiation:
                user_parts.append(f"  Differentiation: {differentiation}")
            # Add narrative context if available — helps LLM write journey-aware UX
            if any([user_journey, product_story, solution_story]):
                user_parts += ["", "Narrative (the product story — use to ground UX in real flows):"]
                if product_story:
                    user_parts.append(f"  Product Story: {product_story}")
                if user_journey:
                    user_parts.append(f"  User Journey: {user_journey}")
                if solution_story:
                    user_parts.append(f"  How It Works: {solution_story}")
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
                f"  Allowed nouns: {vocab_nouns}."
                f"  NEVER use generic SaaS workspace vocabulary: {vocab_banned}."
                "\nFORMAT: Each numbered item is ONE line only. No sub-descriptions, no line breaks within a numbered item."
                "\nUX CONTEXT: After 'TARGET: product', write ONE concise sentence describing the product and who uses it. "
                "  No strategy labels. No truncated decision text. Plain, product-native description only."
                "\nONBOARDING: name the actual first steps in this product — reflect the real product flow, not generic onboarding."
                "  Each step is one short sentence telling the user exactly what to do. No strategy text, no 'Instead of...' framing."
                f"  Use vocabulary from this product domain: {vocab_nouns}."
                "\nEMPTY STATE: explain what is missing at this product stage using product-native language. Guide toward the next concrete action."
                "  Keep copy short — aim for ≤ 12 words each. Name the real thing missing, not 'Add your first item'."
                "\nERROR: short, clear, actionable. Explain what failed and what to do. ≤ 15 words each."
                "  Not generic system errors. Name the product context and the specific failure."
                "\nTOAST: celebrate REAL completed actions in product-specific language. ≤ 8 words each."
                "  NEVER write 'Step complete' or 'Move to the next stage'. "
                "  Confirm the specific thing the user just did."
                "\nBUTTON LABELS: must reflect PRODUCT ACTIONS — not generic app shell (Complete Setup, View My Results, Edit Profile, Save Progress). "
                "  Every label = concrete verb + product object from this domain. All 8 must be actions users do IN THIS product. "
                f"  Use nouns from: {vocab_nouns}. Example buttons for THIS product type: {button_examples}. "
                "  NEVER generic: Complete Setup, View Results, Edit Profile, Save Progress, Get Started, Proceed, Confirm, Continue alone."
                "\nDO NOT reference CLI commands, file paths (brief.json), or internal system workflows (Generate landing, Ollama, Output saved)."
                f"\nBANNED phrases: something went wrong, nothing here yet, your list is empty, check your connection, desired outcome:, differentiation:, instead of generating, step complete, move to the next stage, {vocab_banned}."
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
                f"  Allowed nouns: {vocab_nouns}. "
                f"  NEVER use generic SaaS workspace vocabulary: {vocab_banned}. "
                "ONBOARDING: name the actual first steps users take in this product. Each step is one short sentence — what to do, not what the product is. No strategy framing. "
                f"  Use vocabulary from this product domain: {vocab_nouns}. "
                "EMPTY STATE: name what is missing at this product stage using product-native language. Tell the user the concrete next action. ≤ 12 words per line. "
                "  Not 'Add your first item'. Name the real missing thing. "
                "ERROR: ≤ 15 words each. Short, clear, product-specific. Name the failure and the fix. "
                "  Not generic system messages. "
                "TOAST: ≤ 8 words. Confirm the SPECIFIC action just completed. NEVER write 'Step complete' or 'Move to the next stage'. "
                "  Product-specific milestone language only. "
                "BUTTON LABELS: PRODUCT ACTIONS only — not generic app shell (Complete Setup, View Results, Edit Profile, Save Progress). "
                "  Each label = verb + product object from this domain. Examples: Messaging → Build Brain, Generate Landing. "
                "  Animal welfare → Add Animal, Log Health Check, Add Sponsor. Fintech → Learn My Risk, Complete KYC, Start My SIP. "
                f"  Use nouns from: {vocab_nouns}. Never generic verbs alone. "
                "DO NOT mention CLI commands, file paths (brief.json), or operator workflows. "
                "BANNED: something went wrong, nothing here yet, your list is empty, check your connection, desired outcome:, differentiation:, instead of generating, step complete, move to the next stage, book a short working session, "
                f"{vocab_banned}. "
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
                f"VOCABULARY: Use product-native nouns only — {vocab_nouns}. "
                f"NEVER use: {vocab_banned}. "
                "ONBOARDING: actual product steps, concrete objects, one sentence each. "
                f"  Use vocabulary from this product domain: {vocab_nouns}. "
                "EMPTY STATE: ≤ 12 words. Name what is missing in product terms. Tell the user the next action. "
                "ERROR: ≤ 15 words. Name the failure and the fix in product terms. Not generic system errors. "
                "TOAST: ≤ 8 words. Specific completed action — NEVER 'Step complete' or 'Move to the next stage'. "
                "BUTTON LABELS: PRODUCT ACTIONS only. Concrete verb + product object. No generic shell: Complete Setup, View Results, Edit Profile, Save Progress. "
                f"  Use nouns from: {vocab_nouns}. Domain examples: Build Brain/Generate Landing; Add Animal/Log Health Check; Complete KYC/Start My SIP. "
                "DO NOT mention CLI commands, file paths (brief.json), or tool-specific workflows. "
                "BANNED: something went wrong, nothing here yet, your list is empty, check your connection, desired outcome:, differentiation:, instead of generating, step complete, move to the next stage, "
                f"{vocab_banned}. "
                "Exact headers and counts. No preamble. No bold."
            )
        else:
            system_strict = (
                "UX writer. Output ONLY the document. No preamble. No markdown. No placeholders. "
                "Exact headers: UX CONTEXT, ONBOARDING, EMPTY STATE, ERROR, TOAST, BUTTON LABELS. "
                "ONBOARDING 3 numbered. EMPTY STATE 3. ERROR 3. TOAST 3. BUTTON LABELS 8 numbered. "
                "Banned: streamline, high-quality, unlock, revolutionize, killer app, you know the drill, meh, [insert, [add."
            )

        drift_product = brief.product or ""
        drift_category = decisions.get("category_frame", "") if decisions else ""

        try:
            out = llm_generate(system=system, user=user, model="llama3:8b", temperature=0.3)
            normalized = _normalize_ux_output(out or "")
            if target == "product":
                normalized = _ux_domain_drift_cleanup(normalized, drift_product, drift_category)
                normalized = _clean_ux_context(normalized)
            if _validate_ux_output(normalized, target):
                return (normalized.rstrip("\n") + "\n")
            out = llm_generate(system=system_strict, user=user, model="llama3:8b", temperature=0.2)
            normalized = _normalize_ux_output(out or "")
            if target == "product":
                normalized = _ux_domain_drift_cleanup(normalized, drift_product, drift_category)
                normalized = _clean_ux_context(normalized)
            if _validate_ux_output(normalized, target):
                return (normalized.rstrip("\n") + "\n")
        except Exception:
            pass
        return self._write_ux_pack_fallback(brief, target=target, decisions=decisions)

    def _ux_not_ready_message(self, brief: ClientBrief, nar_filled: int) -> str:
        """Return a readiness message when product narrative is too thin for UX generation."""
        product = clean_phrase(brief.product) or "This product"
        return (
            f"UX GENERATION PAUSED\n\n"
            f"Product: {product}\n"
            f"Narrative fields filled: {nar_filled}/5\n\n"
            f"UX copy requires enough product narrative to ground onboarding, empty states, "
            f"errors, and button labels in real product flows.\n\n"
            f"To proceed:\n"
            f"1. Run --mode brain with a fuller brief (product, audience, pain, offer, context)\n"
            f"2. Or provide more detail via --brief or API overrides\n\n"
            f"The messaging brain needs: product story, user journey, problem story, "
            f"solution story, and transformation narrative.\n"
            f"Once at least 3 of 5 are filled, UX generation will proceed.\n"
        )

    def _write_ux_pack_fallback(self, brief: ClientBrief, target: str = "product", decisions: Optional[dict] = None) -> str:
        """Concrete fallback: no placeholders. Operator = this app; product = from brief."""
        decisions = decisions or {}
        if target == "operator":
            return self._ux_pack_fallback_operator()
        result = self._ux_pack_fallback_product(brief, decisions)
        # Apply drift cleanup and re-validate to ensure fallback is also clean
        drift_product = brief.product or ""
        drift_category = decisions.get("category_frame", "") if decisions else ""
        result = _ux_domain_drift_cleanup(result, drift_product, drift_category)
        return result

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

        # Derive onboarding steps and labels from category keywords; never use shell-native button labels
        # Also check product name and problem/outcome for domain clues when category_frame is empty
        cat_lower = category.lower()
        _product_lower = product.lower()
        _domain_haystack = f"{cat_lower} {_product_lower} {problem.lower()} {outcome.lower()}"
        if any(w in _domain_haystack for w in ("messaging", "positioning", "copy", "content", "launch", "landing", "ux draft")):
            ob1 = f"Define who {product} is for and the problem it solves"
            ob2 = f"Shape your core message — the angle that makes {product} different"
            ob3 = "Generate your first piece and adjust from the result"
            es1 = f"No audience defined yet. Start by telling {product} who you're building for."
            es2 = "No message saved yet. Build your brain to shape your positioning."
            es3 = "No output yet. Generate your first piece."
            t3 = "Messaging brain saved."
            labels = [
                "Build Brain", "Review Brain", "Generate Positioning", "Generate Landing",
                "Generate UX", "Refine Message", "Compare Outputs", "Save Brain",
            ]
        elif any(w in _domain_haystack for w in ("invest", "finance", "sip", "risk", "kyc", "wealth", "fintech")):
            ob1 = "Answer a few questions to understand your financial situation"
            ob2 = f"Complete your verification so {product} can personalise your plan"
            ob3 = "Start your first investment and track your progress"
            es1 = "No risk profile yet. Complete the questionnaire to get started."
            es2 = "No investments set up yet. Finish setup to see your plan."
            es3 = "No transactions yet. Make your first investment to see activity."
            t3 = "Profile complete. Your plan is ready."
            labels = [
                "Learn My Risk", "Complete KYC", "Start My SIP", "Review Plan",
                "View Portfolio", "Confirm Details", "Update Risk Profile", "Track Progress",
            ]
        elif any(w in _domain_haystack for w in ("sanctuary", "shelter", "animal", "care", "rescue", "cow", "gaushala", "welfare")):
            ob1 = f"Register your first animal in {product}"
            ob2 = "Log a health check or feeding record"
            ob3 = "Add a sponsor or track a donation"
            es1 = "No animals registered yet. Add an animal to get started."
            es2 = "No health checks logged yet. Log a health check."
            es3 = "No sponsors or donations yet. Add a sponsor or record a donation."
            t3 = "Animal recorded. Care record updated."
            labels = [
                "Add Animal", "Log Health Check", "Add Sponsor", "Record Feeding",
                "View Care Records", "Track Donation", "Schedule Visit", "Update Shelter Info",
            ]
        elif any(w in _domain_haystack for w in ("influencer", "creator", "match", "brand")):
            ob1 = "Define your brand goal and the audience you want to reach"
            ob2 = "Review creator matches based on your product brief"
            ob3 = "Approve your first creator and go live"
            es1 = "No brand brief yet. Define your goal to see creator matches."
            es2 = "No creators matched yet. Complete your brief to see results."
            es3 = "No creators live yet. Approve a creator to get started."
            t3 = "Creator approved. You are live."
            labels = [
                "Define Brand", "Review Matches", "Approve Creator", "Edit Brief",
                "Save Brief", "Compare Matches", "View Collaborations", "Update Brief",
            ]
        else:
            ob1 = f"Define who {product} is for and the problem it solves"
            ob2 = f"Shape your core message so {product} can tailor output"
            ob3 = f"Generate your first result and refine as you go"
            es1 = f"No audience defined yet. Start by telling {product} who you're building for."
            es2 = "No message saved yet. Build your setup to generate output."
            es3 = "No output yet. Generate your first result."
            t3 = "Brain saved. Output ready."
            labels = [
                "Build Brain", "Review Brain", "Generate Positioning", "Generate Landing",
                "Generate UX", "Refine Message", "Compare Outputs", "Save Brain",
            ]

        # Build a clean UX CONTEXT sentence — no strategy labels, no "Core problem:", no "Goal:"
        if any(w in _domain_haystack for w in ("messaging", "positioning", "copy", "content", "launch", "landing", "ux draft")):
            ux_context_line = f"{product} helps {icp} turn rough product ideas into a clear messaging brain, positioning, landing copy, and UX drafts."
        elif any(w in _domain_haystack for w in ("invest", "finance", "sip", "risk", "kyc", "wealth", "fintech")):
            ux_context_line = f"{product} helps {icp} understand risk, complete KYC, and start their first investment with confidence."
        elif any(w in _domain_haystack for w in ("sanctuary", "shelter", "animal", "care", "rescue", "cow", "gaushala", "welfare")):
            ux_context_line = f"{product} helps {icp} register animals, track health checks, and manage sponsors and donations."
        elif any(w in _domain_haystack for w in ("influencer", "creator", "match", "brand")):
            ux_context_line = f"{product} helps {icp} find the right creators, review matches, and go live with brand collaborations."
        else:
            ux_context_line = f"{product} helps {icp} go from {problem_copy.lower()} to {outcome_copy.lower()}."

        body = f"""UX CONTEXT
TARGET: product
{ux_context_line}

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

    def write_ux_slots(self, brief: ClientBrief) -> dict:
        """Generate core UX copy as a fixed-schema dict.

        Returns exactly these keys (empty string if the model misses one):
          primary_cta, secondary_cta, empty_state, helper_text, error_message
        """
        _SCHEMA = (
            "primary_cta", "secondary_cta", "empty_state",
            "helper_text", "error_message",
        )
        decisions = self.brain_decisions or {}
        pos = self.positioning

        product     = clean_phrase(brief.product) or "the product"
        icp         = (getattr(pos, "icp", "") if pos else "") or decisions.get("icp") or brief.audience or ""
        problem     = (getattr(pos, "core_problem", "") if pos else "") or decisions.get("primary_problem") or brief.pain or ""
        outcome     = (getattr(pos, "promise", "") if pos else "") or decisions.get("desired_outcome") or brief.offer or ""
        diff        = (getattr(pos, "differentiation", "") if pos else "") or decisions.get("differentiation") or ""
        category    = (getattr(pos, "category", "") if pos else "") or decisions.get("category_frame") or ""
        tone        = (brief.tone or "direct and clear").strip()

        # --- generation-time hygiene: normalise before prompt injection ---
        icp         = _strip_product_subject(_prep_ctx(icp, max_words=10), product)
        problem     = _strip_product_subject(_prep_ctx(problem, max_words=14), product)
        outcome     = _prep_ctx(outcome, max_words=12)
        diff        = _prep_ctx(diff, max_words=12)
        category    = _prep_ctx(category, max_words=8)
        tone        = _prep_ctx(tone, max_words=6)

        system = (
            "You are a UX writer for a specific product. Respond with ONLY a valid JSON object — no markdown, no preamble.\n"
            "Keys: primary_cta, secondary_cta, empty_state, helper_text, error_message.\n\n"
            "FIELD RULES:\n"
            "- primary_cta: 2-5 words. The first real action the user takes — from the USER's perspective, not the system's. "
            "Must be user-facing and action-oriented. NEVER use internal product-building language. "
            "BAD: 'Get Started', 'Sign Up', 'Continue', 'Go', 'Proceed', 'Build Brain', 'Define ICP', 'Generate output', 'Create brain', 'Review brief'. "
            "GOOD: 'Start with your idea', 'Try an example', 'Write your first message', 'See example output', 'Add your first item'.\n"
            "- secondary_cta: 2-5 words. A lower-commitment alternative for hesitant users. "
            "Must be different from primary_cta. Must be user-facing — not internal admin language. "
            "BAD: 'Learn More', 'Explore', 'Review brief', 'View brain', 'Check ICP'. "
            "GOOD: 'See example output', 'See how it works', 'View sample results', 'Explore the product'.\n"
            "- empty_state: ≤12 words. What the user sees when the main data object doesn't exist yet. "
            "State what is missing + the ONE action to fix it. "
            "BAD: 'No data available. Start your journey.' GOOD: 'No brain built yet. Paste your idea to start.'.\n"
            "- helper_text: ≤12 words. The label or subtitle for the main input field or first action. "
            "Concrete, instructional, product-native. "
            "BAD: 'Enter your information here'. GOOD: 'Describe your product — who it helps and what it does'.\n"
            "- error_message: ≤12 words. What appears when the primary action fails. "
            "State what failed and one next step. Calm, not alarming. "
            "BAD: 'An error occurred. Please try again.' GOOD: 'Generation failed. Check that Ollama is running.'.\n\n"
            "Banned: unleash, AI-powered, innovative, seamless, powerful solution, next-generation, "
            "revolutionary, journey, experience, ecosystem, unlock, leverage.\n"
            "Every value must feel like it belongs in this specific product's UI — never generic SaaS copy.\n"
            "The response must be a complete JSON object ending with }."
        )

        user_lines = [
            "PRODUCT CONTEXT:",
            f"  Product: {product}",
            f"  Who it is for: {icp}",
            f"  Their problem: {problem}",
        ]
        if outcome:
            user_lines.append(f"  What success looks like: {outcome}")
        if diff:
            user_lines.append(f"  Key differentiator: {diff}")
        if category:
            user_lines.append(f"  Category: {category}")
        user_lines.append(f"  Tone: {tone}")
        user_lines += [
            "",
            "EXAMPLE OUTPUT SHAPE (do NOT copy — write for the product above):",
            '{"primary_cta": "Start with your idea",',
            ' "secondary_cta": "See example output",',
            ' "empty_state": "No brain built yet. Paste your idea to start.",',
            ' "helper_text": "Describe your product — who it helps and what it does.",',
            ' "error_message": "Generation failed. Check that Ollama is running."}',
            "",
            "Return the JSON object now.",
        ]

        try:
            raw = llm_generate(system=system, user="\n".join(user_lines), model="llama3:8b", temperature=0.15)
        except Exception:
            raw = ""
        slots = _extract_slots(raw, _SCHEMA)

        # Validate CTAs; regenerate once if either fails.
        pcta_bad = not _ux_cta_ok(slots.get("primary_cta", ""))
        scta_bad = not _ux_cta_ok(slots.get("secondary_cta", ""))
        if pcta_bad or scta_bad:
            try:
                raw2 = llm_generate(system=system, user="\n".join(user_lines), model="llama3:8b", temperature=0.3)
            except Exception:
                raw2 = ""
            slots2 = _extract_slots(raw2, _SCHEMA)
            if pcta_bad and _ux_cta_ok(slots2.get("primary_cta", "")):
                slots["primary_cta"] = slots2["primary_cta"]
            if scta_bad and _ux_cta_ok(slots2.get("secondary_cta", "")):
                slots["secondary_cta"] = slots2["secondary_cta"]

        return slots
