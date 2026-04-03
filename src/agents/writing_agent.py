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

_LANDING_BANNED = (
    "streamline", "empower", "unlock", "innovative", "cutting-edge", "revolutionize",
    "best-in-class", "game-changing", "stunning", "incredible", "amazing",
    "generic options", "modern platform", "powerful solution", "next generation",
    "seamless experience", "innovative platform", "generic platform",
    "end-to-end", "all-in-one", "game changer", "paradigm",
    "book a short working session", "paste your brief", "request a rewrite",
    "under an hour", "within minutes", "in under", "in minutes",
    "sign up today", "get started today", "step complete", "move to the next stage",
    # Proof placeholder that bleeds across all products
    "early users report clearer messaging",
    # Generic vague WHY phrasing
    "existing tools were not built specifically for this problem",
    "not built specifically for this problem",
)

# ---------------------------------------------------------------------------
# Landing Page Blueprint constants
# ---------------------------------------------------------------------------

_BLUEPRINT_HEADERS = (
    "HERO",
    "PROBLEM",
    "WHY CURRENT OPTIONS FAIL",
    "PRODUCT",
    "PROOF",
    "FINAL CTA",
    "TONE + VOICE",
)

_BLUEPRINT_BANNED = (
    "streamline", "empower", "unlock", "innovative", "cutting-edge", "revolutionize",
    "best-in-class", "game-changing", "seamless experience", "next generation",
    "all-in-one", "innovative platform", "end-to-end", "game changer",
    "powerful solution", "modern platform",
    "sign up today", "get started today",
    "in minutes", "under an hour", "within minutes",
    "synergy", "leverage", "ecosystem", "disrupt",
)


def _normalize_blueprint_output(raw: str) -> str:
    """Strip preamble before first blueprint header; remove markdown heading markers."""
    if not raw or not raw.strip():
        return raw or ""
    t = raw.strip()
    # Find the first recognized ## header and trim preamble before it
    first_idx = len(t)
    for h in _BLUEPRINT_HEADERS:
        for marker in (f"## {h}", f"##{h}"):
            idx = t.find(marker)
            if 0 <= idx < first_idx:
                first_idx = idx
    if first_idx > 0:
        t = t[first_idx:]
    # Normalise bold/plain header variants to the canonical ## format
    for h in _BLUEPRINT_HEADERS:
        t = t.replace(f"**{h}**", f"## {h}")
        t = t.replace(f"**{h}", f"## {h}")
        t = t.replace(f"{h}**", f"## {h}")
        t = t.replace(f"# {h}", f"## {h}")
    return t.strip()


def _validate_blueprint_output(text: str) -> bool:
    """Return True if blueprint has all required headers and minimum content."""
    if not text or len(text.strip()) < 400:
        return False
    if _contains_banned_phrases(text, _BLUEPRINT_BANNED):
        return False
    # Require at least the first 8 core sections
    core_headers = _BLUEPRINT_HEADERS[:8]
    return all(h in text for h in core_headers)


def _blueprint_section_text(text: str, start_header: str, end_header: str) -> str:
    """Extract text between two consecutive blueprint section headers."""
    t = text or ""
    start = t.find(start_header)
    if start < 0:
        return ""
    content_start = start + len(start_header)
    end = t.find(end_header, content_start)
    return t[content_start: end if end > 0 else len(t)].strip()


# Map of domain keywords → concrete behavior-grounded alternative descriptions.
# Values describe what the user *does*, not just the tool name.
_ALT_BEHAVIOR_MAP: dict[str, str] = {
    "messaging":   "manual ChatGPT prompts, copywriters on Upwork, Notion docs that never get used",
    "positioning": "manual ChatGPT prompts, a copywriter, or a Notion doc that stays a draft",
    "landing":     "manual landing page rewrites in Notion, ChatGPT prompt chains, hiring a copywriter",
    "copywriting": "freelance copywriters, ChatGPT prompts, Notion templates that need heavy editing",
    "content":     "freelance writers, ChatGPT with generic prompts, agencies with long revision cycles",
    "ecommerce":   "manual spreadsheets, CRM exports, email campaigns managed in Mailchimp or Klaviyo",
    "retention":   "manual email sequences in Mailchimp, spreadsheet-tracked cohorts, CRM manual follow-up",
    "analytics":   "manual spreadsheet exports, Looker dashboards that take weeks to set up, BI consultants",
    "reporting":   "manual CSV exports, Google Sheets pivot tables, weekly manual reports sent by email",
    "finance":     "spreadsheets, manual QuickBooks reconciliation, a part-time CFO or bookkeeper",
    "inventory":   "Excel/Google Sheets, manual ERP data entry, periodic physical counts",
    "recruiting":  "manual LinkedIn outreach, ATS spreadsheets, job board post-and-pray",
    "hiring":      "LinkedIn job posts, manual resume screening, spreadsheet candidate tracking",
    "sales":       "manual CRM updates in Salesforce/HubSpot, email follow-ups tracked in a spreadsheet",
    "crm":         "spreadsheets, Notion CRM templates, manual email chains",
    "marketing":   "manual ChatGPT prompts, agencies with slow iteration cycles, spreadsheet campaign tracking",
    "scheduling":  "email back-and-forth to find meeting times, Calendly + manual agenda docs",
    "support":     "manual email triage, Intercom set up without automation, spreadsheet ticket tracking",
    "ux":          "user interview notes in Notion, manual UX audits, UX agency retainers",
    "influencer":  "manual DMs and emails to creators, spreadsheet tracking, agencies taking 20% cut",
    "creator":     "manual brand outreach, spreadsheet deal tracking, PDF media kits",
    "saas":        "manual onboarding calls, spreadsheet tracking of user activation, email drip sequences",
    "operations":  "spreadsheets, Notion SOPs that drift out of date, email chains for approvals",
    "onboarding":  "manual onboarding calls, Loom video libraries, email drip sequences with low completion",
    "legal":       "manual contract redlines in Word, email threads, PDFs sent back and forth",
    "healthcare":  "paper-based records, manual EHR entry, phone call scheduling",
    "education":   "manual grading, spreadsheet attendance tracking, PDF handouts",
    # ICP-based fallbacks — matched when category alone doesn't resolve
    "founder":     "manual ChatGPT sessions, a freelance copywriter, or a Notion doc that never ships",
    "startup":     "manual ChatGPT prompts, copywriters on Upwork, or Notion templates that need heavy editing",
    "b2b":         "manual CRM updates in Salesforce/HubSpot, email sequences tracked in spreadsheets, agency retainers",
    "hr":          "LinkedIn outreach, spreadsheet candidate tracking, manual resume screening in email",
    "developer":   "manual documentation, Jira backlog grooming, spreadsheet sprint tracking",
    "coach":       "manual DMs and email follow-ups, spreadsheet client tracking, PDF content packages sent by hand",
    "agency":      "manual client reporting in spreadsheets, email chains for approvals, Notion project docs",
    "freelancer":  "manual invoicing in spreadsheets, email chains for project scope, time tracked by hand",
    "solopreneur": "manual ChatGPT sessions, Notion templates, freelancers hired per project",
    "operator":    "spreadsheets, Notion SOPs, manual email threads for cross-team coordination",
}

# Short tool-name tokens that signal a weak/vague alternative value
_WEAK_ALT_TOKENS = {"gpt", "chatgpt", "ai", "tools", "software", "apps", "solutions", "existing"}

# ICP trailing modifiers that are not role nouns — skip these when extracting icp_noun
_ICP_SKIP_ENDINGS = {
    "pre-launch", "launch", "stage", "early", "based", "focused", "driven", "led",
    "only", "first", "new", "senior", "junior", "small", "large", "mid",
}


def _icp_role_noun(icp: str) -> str:
    """Extract the most role-like noun from an ICP string.

    Truncates at the first relative-clause or prepositional marker ("who", "which",
    "that", "for", "to", "with") so that trailing qualifiers like "who struggle to
    write their landing page" don't produce spurious nouns like "page".
    Then walks from the end of the core words to find the first non-modifier noun.
    """
    words = (icp or "").strip().split()
    if not words:
        return "user"
    # Stop before relative clauses / prepositional tails that follow the role noun
    _CLAUSE_STOPS = {"who", "which", "that", "where", "when", "for", "to", "with", "in", "on", "at", "by"}
    clause_idx = len(words)
    for i, w in enumerate(words):
        if w.lower().rstrip(".,;") in _CLAUSE_STOPS and i > 0:
            clause_idx = i
            break
    core_words = words[:clause_idx]
    for w in reversed(core_words):
        clean = w.lower().rstrip(".,;")
        if clean not in _ICP_SKIP_ENDINGS and len(clean) > 2:
            return clean
    return words[0].lower() if words else "user"


def _expand_alternatives(
    alternative: str, category: str, product: str, icp: str, problem: str
) -> str:
    """Return a concrete, behavior-grounded alternative string.

    If `alternative` is empty, vague, or just tool names without context,
    expand it using category keywords. Prefers concrete user behaviors
    ('manual ChatGPT prompts, Notion docs') over abstract tool names ('AI tools').
    """
    alt_clean = (alternative or "").strip().lower()

    # Treat as weak if blank, very short, or made of generic tokens only,
    # OR if it looks like a constructed LLM boilerplate sentence rather than a real alternative.
    _ALT_BOILERPLATE_STARTS = (
        "existing tools and manual",
        "current tools and manual",
        "existing solutions",
        "existing software",
        "current methods",
        "tools that were not built",
        "not built specifically",
        "manual approaches that",
    )
    words = [w.strip(".,") for w in alt_clean.split()]
    is_weak = (
        not alt_clean
        or len(words) <= 2
        or all(w in _WEAK_ALT_TOKENS for w in words)
        or any(alt_clean.startswith(p) for p in _ALT_BOILERPLATE_STARTS)
    )

    if not is_weak:
        # Already concrete — return as-is preserving original casing
        return alternative.strip()

    # Look up behavior-grounded alternatives from category, product, problem, and ICP context
    combined = f"{category} {product} {problem} {icp}".lower()
    for kw, expanded in _ALT_BEHAVIOR_MAP.items():
        if kw in combined:
            return expanded

    # Generic fallback — still more concrete than "existing tools"
    icp_noun = _icp_role_noun(icp)
    return (
        f"manual workarounds {icp_noun} already use — "
        "spreadsheets, ChatGPT prompts, agencies, or doing it by hand"
    )


def _infer_how_it_works(
    category: str, product: str, icp: str, outcome: str, diff: str, problem: str = ""
) -> str:
    """Infer concrete HOW IT WORKS steps from product context.

    Returns a newline-separated numbered list. Never uses generic bracket placeholders.
    """
    # Search across category, product name, and problem for keyword matching
    cat = f"{category} {product} {problem}".lower()
    out_short = (outcome or "").split(".")[0].strip()[:60]
    icp_noun  = _icp_role_noun(icp)

    if any(k in cat for k in ("positioning", "messaging", "landing", "copywriting")):
        return (
            f"1. Paste your product idea or brief into {product}.\n"
            f"2. {product} extracts your ICP, core problem, and differentiation into the Messaging Brain.\n"
            f"3. Review and edit the Brain fields — refine anything that doesn't fit.\n"
            f"4. Generate your Landing Page Blueprint. Receive a structured PMM document ready to hand to a developer or copywriter."
        )
    if any(k in cat for k in ("analytics", "reporting", "dashboard", "bi")):
        return (
            f"1. Connect your data source or paste your export into {product}.\n"
            f"2. {product} identifies the key signals and surfaces what matters.\n"
            f"3. Review the generated report or dashboard view.\n"
            f"4. Share or export — your team has a clear picture without manual spreadsheet work."
        )
    if any(k in cat for k in ("recruiting", "hiring", "talent")):
        return (
            f"1. Define the role and criteria in {product}.\n"
            f"2. {product} surfaces matching candidates and removes manual screening.\n"
            f"3. Review the shortlist and schedule conversations.\n"
            f"4. Move candidates through stages without spreadsheet tracking."
        )
    if any(k in cat for k in ("ecommerce", "retention", "crm", "sales", "churn", "at-risk", "renewal")):
        return (
            f"1. Connect your store or CRM data to {product}.\n"
            f"2. {product} identifies at-risk customers using purchase behavior signals — before they churn.\n"
            f"3. Review the priority list and trigger targeted follow-ups or recovery messages.\n"
            f"4. Track recovery rate — see which customer segments respond and measure the impact on retention."
        )
    if any(k in cat for k in ("scheduling", "calendar", "booking")):
        return (
            f"1. Share your {product} booking link with the other party.\n"
            f"2. {product} finds the best overlap without email back-and-forth.\n"
            f"3. Both parties confirm in one click.\n"
            f"4. Meeting is scheduled with agenda, reminders, and follow-up set automatically."
        )
    if any(k in cat for k in ("onboarding", "saas", "activation")):
        return (
            f"1. New user signs up and completes the initial intake in {product}.\n"
            f"2. {product} walks them through the core flow step-by-step.\n"
            f"3. User completes their first key action — the moment of value.\n"
            f"4. {product} confirms completion and suggests the next step."
        )
    if any(k in cat for k in ("content", "writing", "creator", "influencer")):
        return (
            f"1. Describe your product, brand, or campaign brief in {product}.\n"
            f"2. {product} generates a structured draft or outreach plan.\n"
            f"3. Review and edit to match your voice.\n"
            f"4. Publish or send — without a freelancer or a blank-page session."
        )
    # Generic but still concrete — better than bracket placeholders
    return (
        f"1. {icp_noun.capitalize()} describes their goal or inputs the core context.\n"
        f"2. {product} processes the input and surfaces the relevant output.\n"
        f"3. {icp_noun.capitalize()} reviews, refines, and confirms the result.\n"
        f"4. {out_short or 'The outcome'} is delivered — without the manual overhead."
    )


def _infer_proof_suggestions(
    category: str, product: str, icp: str, outcome: str, problem: str = ""
) -> str:
    """Return 2–3 grounded proof type suggestions for the blueprint's PROOF section."""
    # Search across category, product name, and problem for keyword matching
    cat      = f"{category} {product} {problem}".lower()
    icp_noun = _icp_role_noun(icp)
    out_short = (outcome or "the core outcome").split(".")[0].strip()[:60]

    icp_sing = icp_noun.rstrip("s") if icp_noun.endswith("s") and len(icp_noun) > 3 else icp_noun
    if any(k in cat for k in ("positioning", "messaging", "landing", "copywriting")):
        return (
            f"{icp_sing.capitalize()} quote — a {icp_sing} who used {product} to write their first landing page "
            f"and describes what changed: add quote + name + company.\n"
            f"Before/after — screenshot of the blank doc vs the finished Blueprint output.\n"
            f"Activation stat — percentage of {icp_noun} who generate a Blueprint in session 1: add number when measured."
        )
    if any(k in cat for k in ("analytics", "reporting", "dashboard")):
        return (
            f"Time-to-insight stat — average time from data import to first report: add number when measured.\n"
            f"User quote — a {icp_noun} who replaced their weekly manual report process: add quote + name.\n"
            f"Integration proof — logos of data sources {product} connects to: add list when ready."
        )
    if any(k in cat for k in ("ecommerce", "retention", "crm", "churn", "at-risk", "renewal")):
        return (
            f"Outcome stat — {icp_sing.capitalize()}s who connect {product} see X% improvement in 30-day retention: add when measured.\n"
            f"{icp_sing.capitalize()} quote — a {icp_sing} who describes the specific account or recovery result: add quote + company name.\n"
            f"Before/after — accounts flagged as at-risk before vs after using {product}: what was caught, what was retained."
        )
    if any(k in cat for k in ("saas", "onboarding", "activation")):
        return (
            f"Activation stat — percentage of new {icp_noun} who complete first key action in session 1: add when measured.\n"
            f"{icp_sing.capitalize()} quote — someone who completed onboarding and describes the experience: add quote + name.\n"
            f"Comparison — time to value vs previous manual process or alternative tool: add when measured."
        )
    # Generic grounded fallback
    return (
        f"{icp_sing.capitalize()} quote — a {icp_sing} who reached {out_short}: add quote + name + context.\n"
        f"Outcome stat — concrete metric tied to {out_short}: add when measured.\n"
        f"Demo or walkthrough — a 60-second video or screenshot sequence of the first session."
    )


def _precompute_pmm_analysis(
    product: str, category: str, icp: str,
    core_problem: str, alternative: str,
    outcome: str, diff: str,
) -> dict:
    """Pre-compute a PMM analysis block for the blueprint prompt.

    Returns four strings the LLM can use directly instead of reasoning from scratch.
    All inference is rule-based — no LLM call.
    """
    icp_noun = _icp_role_noun(icp) if icp else "user"
    cat_lower = (category or "").lower()
    prob_short = (core_problem or "").split(".")[0].strip()[:80]
    out_short = (outcome or "").split(".")[0].strip()[:80]
    diff_short = (diff or "").split(".")[0].strip()[:80]

    # --- Product mechanism ---
    if diff_short:
        mechanism = f"{product} {diff_short[0].lower()}{diff_short[1:]}"
    elif cat_lower:
        mechanism = f"{product} is a {category} that helps {icp_noun}s {prob_short[0].lower()}{prob_short[1:]}" if prob_short else f"{product} is a {category}"
    else:
        mechanism = f"{product} helps {icp_noun}s solve: {prob_short}" if prob_short else product

    # --- User job ---
    if out_short:
        user_job = f"{icp_noun.capitalize()}s need to {out_short[0].lower()}{out_short[1:]}"
    elif prob_short:
        user_job = f"{icp_noun.capitalize()}s need to fix: {prob_short}"
    else:
        user_job = f"{icp_noun.capitalize()}s need a better way to do this"

    # --- Before / After ---
    before = prob_short if prob_short else "current workflow is manual and slow"
    after = out_short if out_short else "a clear, actionable result"
    before_after = f"Before: {before}. After: {after}"

    # --- Expanded alternatives with failure reasons ---
    alt_items = [a.strip() for a in (alternative or "").split(",") if a.strip()]
    expanded_alts: list[str] = []
    # Map of tool keywords to their structural failure
    _ALT_FAILURES = {
        "chatgpt": "produces generic copy because it has no product context or positioning decisions",
        "gpt": "produces generic copy because it has no product context or positioning decisions",
        "notion": "stores notes but does not extract decisions or generate structured output",
        "spreadsheet": "tracks data but cannot analyze patterns or recommend actions",
        "agency": "takes weeks and costs thousands for a single iteration cycle",
        "agencies": "take weeks and cost thousands for a single iteration cycle",
        "freelance": "writes from a brief they received, not from product positioning data",
        "copywriter": "writes from a brief they received, not from product positioning data",
        "consultant": "provides advice but the founder still has to do all the execution",
        "manual": "requires hours of repetitive work and produces inconsistent results",
        "template": "provides structure but no product-specific content or decisions",
        "crm": "tracks contacts but does not diagnose why customers leave or what to do about it",
        "klaviyo": "sends emails but does not identify which customers are at risk or why",
        "mailchimp": "sends campaigns but cannot diagnose retention problems or personalize recovery",
        "dashboard": "shows numbers but does not explain what they mean or what to do next",
        "looker": "builds reports but requires a data team to set up and maintain",
        "hubspot": "manages the pipeline but does not help with messaging or positioning",
        "salesforce": "tracks deals but does not help write the outreach or positioning",
    }
    for alt in alt_items[:4]:
        alt_lower = alt.strip().lower()
        failure = ""
        for kw, reason in _ALT_FAILURES.items():
            if kw in alt_lower:
                failure = reason
                break
        if failure:
            expanded_alts.append(f"{alt} — {failure}")
        else:
            expanded_alts.append(f"{alt} — does not solve the specific problem of {prob_short[:50]}")

    if not expanded_alts:
        expanded_alts = [f"Manual workarounds — {icp_noun}s cobble together spreadsheets, emails, and generic tools"]

    return {
        "product_mechanism": mechanism,
        "user_job": user_job,
        "before_after": before_after,
        "expanded_alternatives": expanded_alts,
    }


def _clean_category(category: str, product: str, problem: str = "") -> str:
    """Return a clean, short category label suitable for use in sentences.

    Strips the product name, leading prepositions, and audience qualifiers.
    If the result still looks like ICP text rather than a category label,
    infers the category from product/problem keywords.
    """
    import re as _re

    cat = (category or "").strip().rstrip(".")
    if not cat:
        return "focused tool"

    # Strip product name from start
    if product and cat.lower().startswith(product.lower()):
        cat = cat[len(product):].lstrip(" -—:").strip()

    # Strip leading prepositions (e.g. "for b2b saas operators...")
    cat = _re.sub(r"^(for|in|from|of|by|to)\s+", "", cat, flags=_re.IGNORECASE).strip()

    # Strip audience/relative-clause tails: " for X", " who X", " that X", " which X"
    cat = _re.sub(
        r"\s+(for|with|who|that|which|where|when)\s+.+$", "", cat, flags=_re.IGNORECASE
    ).strip().rstrip(".")

    # Take first 4 words
    words = cat.split()
    result = " ".join(words[:4]) if words else ""

    # If result is empty or looks like ICP text (all audience/role words), infer from keywords
    _ICP_INDICATOR_WORDS = {
        "operators", "founders", "managers", "teams", "users", "saas", "b2b",
        "startups", "companies", "businesses", "professionals",
    }
    result_words = set(result.lower().split()) if result else set()
    is_icp_leakage = not result or result_words.issubset(_ICP_INDICATOR_WORDS)

    if is_icp_leakage:
        combined = f"{product} {problem}".lower()
        if any(k in combined for k in ("churn", "retention", "at-risk", "renewal", "cancellation")):
            return "churn prediction"
        if any(k in combined for k in ("landing", "hero section", "homepage", "copy", "positioning")):
            return "landing page positioning"
        if any(k in combined for k in ("hiring", "recruiting", "candidate", "talent")):
            return "recruiting"
        if any(k in combined for k in ("analytics", "dashboard", "reporting", "metrics", "bi")):
            return "product analytics"
        if any(k in combined for k in ("email", "outreach", "campaign", "messaging")):
            return "outreach automation"
        if any(k in combined for k in ("onboarding", "activation", "saas")):
            return "product onboarding"
        if any(k in combined for k in ("sales", "pipeline", "deal", "crm")):
            return "sales intelligence"
        return "focused tool"

    return result


def _fix_blueprint_product_name(text: str, product: str, icp: str) -> str:
    """Post-process: correct LLM product naming bug where an ICP noun is used as the product name.

    Catches patterns like 'Founders is a ...' or 'Founder is a ...' when the product is 'Scriptly'.
    Replaces with '{product} is a ...' in POSITIONING SUMMARY and PRODUCT EXPLANATION.
    """
    if not text or not icp:
        return text
    product_cap = product.strip()
    # Collect candidate ICP nouns: last word of ICP (singular + plural)
    icp_last_raw = icp.strip().split()[-1].rstrip(".").strip()
    candidates = {icp_last_raw.capitalize(), icp_last_raw.rstrip("s").capitalize()}
    candidates.discard(product_cap)
    if not candidates:
        return text
    fixed = text
    for candidate in candidates:
        if candidate.lower() == product_cap.lower():
            continue
        # Replace "{Candidate} is a/an" with "{product} is a/an"
        fixed = re.sub(
            rf"\b{re.escape(candidate)}s?\s+is an?\b",
            f"{product_cap} is a",
            fixed,
        )
        # Replace "{Candidate} is built" with "{product} is built"
        fixed = re.sub(
            rf"\b{re.escape(candidate)}s?\s+is built\b",
            f"{product_cap} is built",
            fixed,
        )
        # Replace "{Candidate} helps" with "{product} helps"
        fixed = re.sub(
            rf"\b{re.escape(candidate)}s?\s+helps?\b",
            f"{product_cap} helps",
            fixed,
        )
        # Replace "Product: {Candidate} —" or "Product: {Candidate}." in POSITIONING SUMMARY
        fixed = re.sub(
            rf"(Product:\s+){re.escape(candidate)}s?\b",
            rf"\g<1>{product_cap}",
            fixed,
        )
    return fixed


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


def _strip_landing_preamble(text: str) -> str:
    """Strip any LLM preamble that appears before the HEADLINE header."""
    if not text:
        return text
    idx = text.find("HEADLINE")
    if idx > 0 and text[:idx].strip():
        return text[idx:]
    return text


_TRAILING_CONJ = frozenset({"and", "or", "with", "for", "to", "the", "a", "an", "of", "in"})

def _cleanup_landing_output(text: str) -> str:
    """Post-process cleanup: fix trailing-conjunction headlines and two-sentence subheads."""
    if not text:
        return text
    lines = text.splitlines(keepends=True)
    result = []
    prev_header = ""
    for line in lines:
        stripped = line.rstrip("\n").strip()
        if stripped in ("HEADLINE", "SUBHEADLINE", "WHAT THIS IS", "WHO IT IS FOR", "THE PROBLEM",
                        "WHY EXISTING TOOLS FAIL", "HOW IT WORKS",
                        "KEY BENEFITS", "CALL TO ACTION"):
            prev_header = stripped
            result.append(line)
            continue
        if prev_header == "HEADLINE" and stripped:
            words = stripped.split()
            while words and words[-1].lower().rstrip(".,") in _TRAILING_CONJ:
                words.pop()
            cleaned = " ".join(words)
            result.append(cleaned + ("\n" if line.endswith("\n") else ""))
            prev_header = ""
            continue
        if prev_header == "SUBHEADLINE" and stripped:
            # "For X. Y." → "For X, y." — join two-sentence subheads into one
            if re.search(r'\. [A-Z]', stripped):
                parts = re.split(r'\. ', stripped, maxsplit=1)
                if len(parts) == 2:
                    stripped = f"{parts[0].rstrip('.')}, {lower_first(parts[1])}".rstrip(".") + "."
            result.append(stripped + ("\n" if line.endswith("\n") else ""))
            prev_header = ""
            continue
        if stripped:
            prev_header = ""
        result.append(line)
    return "".join(result)


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
    # Strategy layers — set by main.py / API before calling generators.
    # When set, generators use these for deeper product-grounded output.
    positioning: Optional[object] = None   # PositioningContext
    narrative: Optional[object] = None     # NarrativeContext

    def write_landing_page(self, brief: ClientBrief) -> str:
        """Generate landing page from positioning + narrative contexts via LLM; fallback to rule-based template if invalid."""
        decisions = self.extract_positioning_decisions(brief)
        pos = self.positioning  # PositioningContext (may be None for backward compat)
        nar = self.narrative    # NarrativeContext (may be None for backward compat)

        _LANDING_HEADERS = (
            "HEADLINE", "SUBHEADLINE", "WHAT THIS IS", "WHO IT IS FOR", "THE PROBLEM",
            "WHY EXISTING TOOLS FAIL", "HOW IT WORKS", "KEY BENEFITS", "CALL TO ACTION",
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
            first = _section_first_line(text, "HEADLINE", "SUBHEADLINE")
            if not first:
                return True
            words = first.split()
            if len(words) > 10:
                return False
            lower = first.strip().lower()
            if ":" in first:
                return False
            _INF_STARTS = (
                "to help ", "to simplify ", "to develop ", "to enable ", "to make ",
                "to build ", "to create ", "to provide ", "to give ", "to allow ",
                "to ensure ", "to support ", "to deliver ",
            )
            for bad in _INF_STARTS:
                if lower.startswith(bad):
                    return False
            return True

        def _subhead_ok(text: str) -> bool:
            first = _section_first_line(text, "SUBHEADLINE", "WHAT THIS IS")
            return len(first.split()) <= 20 if first else True

        def _who_its_for_ok(text: str) -> bool:
            """WHO IT IS FOR must be a noun phrase (user type only), not an action or outcome."""
            first = _section_first_line(text, "WHO IT IS FOR", "THE PROBLEM")
            if not first or len(first.strip()) < 5:
                return True
            lower = first.strip().lower()
            verb_starts = ("simplify", "complete", "develop", "make ", "help ", "enable ", "empower ")
            if any(lower.startswith(v) for v in verb_starts):
                return False
            first_word = lower.split()[0] if lower.split() else ""
            if first_word in ("to", "for") and len(lower.split()) > 1:
                second = lower.split()[1]
                if second in ("simplify", "complete", "develop", "help", "make", "enable"):
                    return False
            return True

        def _sections_distinct(text: str) -> bool:
            problem_text = _section_first_line(text, "THE PROBLEM", "WHY EXISTING TOOLS FAIL")
            why_text = _section_first_line(text, "WHY EXISTING TOOLS FAIL", "HOW IT WORKS")
            if not problem_text or not why_text:
                return True
            p_words = set(problem_text.lower().split())
            w_words = set(why_text.lower().split())
            if not p_words or not w_words:
                return True
            overlap = len(p_words & w_words) / min(len(p_words), len(w_words))
            return overlap < 0.6

        def _what_this_is_ok(text: str) -> bool:
            """WHAT THIS IS must be: CATEGORY + MECHANISM + PRODUCT ACTION.

            Must contain a mechanism verb AND read as a complete sentence.
            Rejects vague broad descriptions and shorthand fragments.
            """
            content = _section_first_line(text, "WHAT THIS IS", "WHO IT IS FOR")
            if not content or len(content.strip()) < 20:
                return False
            lower = content.strip().lower()
            mechanism_verbs = ("turns", "helps", "guides", "tracks", "manages", "explains", "generates", "records", "creates", "builds", "completes", "registers")
            if not any(v in lower for v in mechanism_verbs):
                return False
            # Reject vague broad category descriptions
            _WHAT_THIS_IS_BANNED = (
                "product development and marketing",
                "product development",
                "marketing for",
                "development and marketing",
                "solutions for",
                "services for",
                "platform for companies",
                "tool for companies using",
            )
            if any(b in lower for b in _WHAT_THIS_IS_BANNED):
                return False
            # Reject shorthand parenthetical fragments like "(KYC, risk, SIP)"
            if re.search(r"\([^)]{3,30}\)$", content.strip()):
                return False
            # Must be a proper sentence (≥8 words)
            if len(content.strip().split()) < 8:
                return False
            return True

        def _diff_ok(text: str) -> bool:
            """HOW IT WORKS must not be a near-duplicate of WHAT THIS IS."""
            what = _section_first_line(text, "WHAT THIS IS", "WHO IT IS FOR")
            how = _section_first_line(text, "HOW IT WORKS", "KEY BENEFITS")
            if not what or not how:
                return True
            w_words = set(what.lower().split())
            h_words = set(how.lower().split())
            if not w_words or not h_words:
                return True
            overlap = len(w_words & h_words) / min(len(w_words), len(h_words))
            return overlap < 0.6

        def _valid(out: str) -> bool:
            return (
                bool(out)
                and _validate_headers(out, _LANDING_HEADERS)
                and not _contains_banned_phrases(out, _LANDING_BANNED)
                and not _headline_has_question(out)
                and _headline_ok(out)
                and _subhead_ok(out)
                and _who_its_for_ok(out)
                and _sections_distinct(out)
                and _what_this_is_ok(out)
                and _diff_ok(out)
            )

        # Extract positioning fields from PositioningContext if available, else from decisions
        icp = (getattr(pos, "icp", "") if pos else "") or decisions.get("icp", "")
        core_problem = (getattr(pos, "core_problem", "") if pos else "") or decisions.get("primary_problem", "")
        enemy = (getattr(pos, "enemy", "") if pos else "") or decisions.get("current_alternative", "")
        promise = (getattr(pos, "promise", "") if pos else "") or decisions.get("desired_outcome", "")
        category = (getattr(pos, "category", "") if pos else "") or decisions.get("category_frame", "")
        differentiation = (getattr(pos, "differentiation", "") if pos else "") or decisions.get("differentiation", "")
        anti_positioning = (getattr(pos, "anti_positioning", "") if pos else "") or decisions.get("anti_positioning", "")

        # Extract narrative fields if available
        product_story = getattr(nar, "product_story", "") if nar else ""
        problem_story = getattr(nar, "problem_story", "") if nar else ""
        user_journey = getattr(nar, "user_journey", "") if nar else ""
        transformation = getattr(nar, "transformation", "") if nar else ""
        solution_story = getattr(nar, "solution_story", "") if nar else ""

        system = (
            "You are a senior product marketer writing a landing page for a real product launch. "
            "Your output must read like strategic product copy — not a filled template. "
            "Every section must feel connected. The page should tell a coherent story from headline to call to action. "
            "\n"
            "SECTION RULES (apply to every section): "
            "Each section must contain 1–3 sentences. "
            "Never omit a section. "
            "If context is missing for a section, infer a reasonable statement using the Brain fields provided. "
            "\n"
            "HEADLINE: max 10 words. Express the OUTCOME the user gets — not a description of the ICP, not a question, not a slogan. "
            "  NO colon. NO phrases like 'to help', 'to simplify', 'to develop', 'to enable'. "
            "  Sharp, specific, declarative. Example: 'Turn messy product ideas into clear messaging.' "
            "SUBHEADLINE: max 20 words. One sentence. Product + mechanism (what it is and how it works). "
            "WHAT THIS IS: CATEGORY + MECHANISM. One sentence naming the category and how it works. "
            "  Examples: 'An AI messaging workspace that turns rough product thinking into positioning, landing copy, and UX drafts.' "
            "  'A guided onboarding assistant that explains risk, completes KYC, and helps new investors start their first SIP.' "
            "  'A welfare management tool for registering animals, tracking health checks, and managing sponsors.' "
            "  NOT vague (e.g. 'Product development and marketing for B2B SaaS companies'). "
            "  NOT shorthand (e.g. 'Fintech onboarding for first-time investors (KYC, risk, SIP)'). "
            "  Must be a full sentence with ≥ 8 words. Must contain a mechanism verb (turns, helps, guides, tracks, manages, explains, generates, records, creates, builds, completes, registers). "
            "WHO IT IS FOR: A noun phrase only — the user type. Examples: 'First-time retail investors in India.', 'B2B SaaS founders launching new products.', 'Gaushala managers responsible for non-milking cows.' "
            "  NO verbs like simplify / complete / develop. NO action or outcome — only who they are. "
            "THE PROBLEM: The user's lived experience of the friction. Write it as if describing their actual day. "
            "  Do NOT name alternatives here — focus on what the user FEELS and DOES. "
            "WHY EXISTING TOOLS FAIL: Name the specific ENEMY (the current alternative). "
            "  Explain the structural flaw — why it was never designed for this problem. "
            "  This section advances the argument beyond THE PROBLEM. Never repeat the pain — explain the gap. "
            "HOW IT WORKS: Describe the product's core mechanism in plain terms. "
            "  1–3 sentences. Walk through the key step or flow that delivers the outcome. "
            "  Must say something new — do not repeat WHAT THIS IS. "
            "KEY BENEFITS: The concrete wins the user gets. No fabricated stats. No time claims. "
            "  1–3 sentences. Grounded in real product behavior. "
            "CALL TO ACTION: One line. Product-specific action tied to the promise. Not 'Sign up today'. "
            "\n"
            "WRITING RULES: "
            "Vary sentence length. Use concrete nouns over abstract ones. "
            "Each section must advance the argument — never restate what a previous section said. "
            "Write prose, not bullet points. The page should flow as a single persuasive arc. "
            "\n"
            "Banned: streamline, empower, unlock, innovative, cutting-edge, revolutionize, best-in-class, game-changing, "
            "generic options, modern platform, powerful solution, next generation, seamless experience, all-in-one, "
            "under an hour, in minutes, sign up today, get started today. "
            "\n"
            "Headers in EXACT order: HEADLINE, SUBHEADLINE, WHAT THIS IS, WHO IT IS FOR, THE PROBLEM, "
            "WHY EXISTING TOOLS FAIL, HOW IT WORKS, KEY BENEFITS, CALL TO ACTION. "
            "Output only the document. No preamble."
        )
        system_strict = (
            "Senior product marketer. STRICT format. "
            "Every section: 1–3 sentences. Never omit a section. Infer from Brain fields if context is missing. "
            "HEADLINE: max 10 words, outcome only. No colon. No 'to help/simplify/develop'. "
            "SUBHEADLINE: max 20 words, one sentence, product + mechanism. "
            "WHAT THIS IS: category + mechanism (how it works). Full sentence ≥ 8 words. Must contain a mechanism verb (turns/helps/guides/tracks/manages/explains/generates/records/creates/builds/completes/registers). Not vague. Not shorthand. "
            "WHO IT IS FOR: noun phrase only (user type). No verbs like simplify/complete/develop. "
            "THE PROBLEM: user's lived pain, no alternatives mentioned. "
            "WHY EXISTING TOOLS FAIL: name the enemy, explain structural flaw, do NOT repeat THE PROBLEM. "
            "HOW IT WORKS: core mechanism in plain terms, 1–3 sentences, must say something new vs WHAT THIS IS. "
            "KEY BENEFITS: concrete wins, no stats, no time claims, 1–3 sentences. "
            "CALL TO ACTION: one line, product verb. "
            "Advance argument across sections. No repetition. Prose, not bullets. "
            "Headers: HEADLINE, SUBHEADLINE, WHAT THIS IS, WHO IT IS FOR, THE PROBLEM, WHY EXISTING TOOLS FAIL, HOW IT WORKS, KEY BENEFITS, CALL TO ACTION. "
            "No banned phrases. Output only."
        )

        # Build user prompt with both positioning AND narrative context
        benefits_fallback = (
            f"concrete wins tied to the specific outcome ({promise[:60] if promise else ''}); "
            "no time claims, no stats, no made-up data"
        )
        user_parts = [
            f"Write a landing page for: {brief.product or 'Not specified'}",
            "",
            "=== POSITIONING (what this product IS) ===",
            f"  Promise: {promise}",
            f"  ICP: {icp}",
            f"  Core Problem: {core_problem}",
            f"  Enemy (current alternative): {enemy}",
            f"  Category: {category}",
            f"  Differentiation: {differentiation}",
            f"  Anti-Positioning (what this is NOT): {anti_positioning}",
        ]

        # Add narrative context if available — this gives the LLM deeper product understanding
        if any([product_story, problem_story, transformation, solution_story]):
            user_parts += [
                "",
                "=== NARRATIVE (the story behind the product) ===",
            ]
            if product_story:
                user_parts.append(f"  Product Story: {product_story}")
            if problem_story:
                user_parts.append(f"  Problem Story: {problem_story}")
            if user_journey:
                user_parts.append(f"  User Journey: {user_journey}")
            if transformation:
                user_parts.append(f"  Transformation: {transformation}")
            if solution_story:
                user_parts.append(f"  Solution Story: {solution_story}")

        user_parts += [
            "",
            f"Tone: {brief.tone or 'Clear and direct'}",
            "",
            "=== SECTION MAPPING (use as guide, do not include in output) ===",
            f"  HEADLINE ← promise: {promise}",
            f"  SUBHEADLINE ← product + mechanism: {category or promise}",
            f"  WHAT THIS IS ← solution story: {solution_story or category}",
            f"  WHO IT IS FOR ← icp: {icp}",
            f"  THE PROBLEM ← problem story: {problem_story or core_problem}",
            f"  WHY EXISTING TOOLS FAIL ← name '{enemy}' specifically; explain why that approach structurally fails for this problem (not why the problem is hard — why THAT alternative misses it)",
            f"  HOW IT WORKS ← differentiation: {differentiation} — describe the core step or flow that delivers the outcome; must say something NEW beyond WHAT THIS IS",
            f"  KEY BENEFITS ← {transformation or benefits_fallback}",
            f"  CALL TO ACTION ← promise: {promise}",
            "",
            "Output the document. No preamble.",
        ]
        user = "\n".join(user_parts)

        out = _run_with_retry(
            generate_fn=lambda: llm_generate(system=system, user=user, model="llama3:8b", temperature=0.3),
            strict_generate_fn=lambda: llm_generate(system=system_strict, user=user, model="llama3:8b", temperature=0.25),
            validator_fn=_valid,
        )
        if out:
            return (_cleanup_landing_output(_strip_landing_preamble(out)).rstrip("\n") + "\n")
        return self._write_landing_page_fallback(brief, decisions)

    # -------------------------------------------------------------------
    # Landing Page Blueprint (new primary artifact)
    # -------------------------------------------------------------------

    def write_landing_blueprint(self, brief: ClientBrief) -> str:
        """Generate a structured Landing Page Blueprint — a PMM strategy document.

        Uses Messaging Brain + idea/brief context. Infers missing strategy carefully.
        Returns a 10-section document that guides copywriting and frontend implementation.
        """
        decisions = self.brain_decisions or {}
        pos = self.positioning
        nar = self.narrative

        # Resolve fields: positioning context > brain decisions > brief
        product      = clean_phrase(brief.product) or "the product"
        icp          = (getattr(pos, "icp", "") if pos else "") or decisions.get("icp", "") or clean_phrase(brief.audience) or ""
        core_problem = (getattr(pos, "core_problem", "") if pos else "") or decisions.get("primary_problem", "") or clean_sentence(brief.pain or "") or ""
        alternative  = (getattr(pos, "enemy", "") if pos else "") or decisions.get("current_alternative", "") or ""
        diff         = (getattr(pos, "differentiation", "") if pos else "") or decisions.get("differentiation", "") or ""
        outcome      = (getattr(pos, "promise", "") if pos else "") or decisions.get("desired_outcome", "") or clean_phrase(brief.offer or "") or ""
        category_raw = (getattr(pos, "category", "") if pos else "") or decisions.get("category_frame", "") or ""
        category     = _clean_category(category_raw, product, core_problem)
        anti         = (getattr(pos, "anti_positioning", "") if pos else "") or decisions.get("anti_positioning", "") or ""
        tone         = (brief.tone or "").strip()

        # Narrative context
        product_story  = getattr(nar, "product_story",  "") if nar else ""
        problem_story  = getattr(nar, "problem_story",  "") if nar else ""
        transformation = getattr(nar, "transformation", "") if nar else ""

        # Expand weak or missing alternatives into concrete, behavior-grounded suggestions
        alt_for_prompt = _expand_alternatives(alternative, category, product, icp, core_problem)
        alt_is_inferred = not alternative.strip()

        # Infer concrete HOW IT WORKS steps from category + product context
        how_it_works_hint = _infer_how_it_works(category, product, icp, outcome, diff, core_problem)

        # Infer proof type suggestions — injected into LLM prompt so it generates real suggestions
        proof_hint = _infer_proof_suggestions(category, product, icp, outcome, core_problem)

        system = (
            "You are a senior product marketing strategist writing a Landing Page Blueprint. "
            "Output EXACTLY 7 sections in this exact order, with EXACTLY these ## headers:\n"
            "## HERO, ## PROBLEM, ## WHY CURRENT OPTIONS FAIL, ## PRODUCT, ## PROOF, ## FINAL CTA, ## TONE + VOICE\n\n"

            "FORMAT — MANDATORY, NO EXCEPTIONS:\n"
            "- Every section header: ## SECTIONNAME (all caps, two hashes, one space)\n"
            "- Every field: label line (plain text, no formatting) followed immediately by the value "
            "on the next line in double quotes\n"
            "- If a field has no content: write the label, then \"—\" as the value\n"
            "- Notes is always the last field in each section\n"
            "- No markdown bold (**), no bullet points, no numbered lists, no extra formatting\n"
            "- Output NOTHING outside these 7 sections — no preamble, no summary, no closing remarks\n\n"

            "EXACT SECTION STRUCTURE TO FOLLOW:\n\n"

            "## HERO\n"
            "Headline\n"
            "\"[≤10-word outcome — no colon, no question mark, no product name]\"\n\n"
            "Subhead\n"
            "\"[≤20 words. Pattern: {product} helps [ICP] [action] without [old way]]\"\n\n"
            "CTA\n"
            "\"[2-4 word verb-led button label]\"\n\n"
            "Notes\n"
            "\"[Tone and placement guidance]\"\n\n"

            "## PROBLEM\n"
            "Core problem statement\n"
            "\"[One sentence describing the pain]\"\n\n"
            "Stakes\n"
            "\"[What happens if this goes unsolved]\"\n\n"
            "Notes\n"
            "\"[Optional framing notes, or —]\"\n\n"

            "## WHY CURRENT OPTIONS FAIL\n"
            "\"[Name each alternative and what it does wrong structurally. One paragraph.]\"\n\n"
            "Notes\n"
            "\"[Optional, or —]\"\n\n"

            "## PRODUCT\n"
            "One-liner\n"
            "\"[[Product] is a [category] that [mechanism]]\"\n\n"
            "How it works\n"
            "\"[Step 1 / Step 2 / Step 3 — name specific inputs, actions, outputs]\"\n\n"
            "Key differentiator\n"
            "\"[What makes this different from alternatives]\"\n\n"
            "Notes\n"
            "\"[Optional, or —]\"\n\n"

            "## PROOF\n"
            "\"[Specific metric, quote, or credibility signal. "
            "Write 'add when measured' if number is unknown — never use [brackets].]\"\n\n"
            "Notes\n"
            "\"[Optional, or —]\"\n\n"

            "## FINAL CTA\n"
            "Headline\n"
            "\"[Closing line — complete sentence, names the specific artifact or outcome after session 1]\"\n\n"
            "CTA\n"
            "\"[2-4 word verb-led label]\"\n\n"
            "Notes\n"
            "\"[Optional, or —]\"\n\n"

            "## TONE + VOICE\n"
            "Tone\n"
            "\"[2-3 adjectives describing the voice]\"\n\n"
            "Words to avoid\n"
            "\"[5-8 specific banned words for this product]\"\n\n"

            "CONTENT RULES — MANDATORY:\n"
            f"- Product name is '{product}'. The ICP/audience is '{icp}'. "
            "These are different — never use the ICP as the product name.\n"
            "- Headline: ≤10 words. Standalone outcome. No colon. No question mark. No product name. "
            "Not 'stop guessing'. Not 'sharper communication'. Name what specifically improves.\n"
            "- Subhead: ≤20 words. Must not repeat the headline. "
            "Must not just restate product + mechanism.\n"
            "- CTA: 2-4 words, verb-led. "
            "Good: 'Paste your idea', 'See a demo'. "
            "Bad: 'Start with ProductName', 'Get Started', 'Sign Up', 'Unlock', 'Transform'.\n"
            "- WHY CURRENT OPTIONS FAIL: Name each alternative and what it does wrong structurally. "
            "Never write '[tool] was not built for this'. Instead: '[tool] does X which causes Y'.\n"
            "- One-liner: Pattern '[Product] is a [category] that [mechanism]'. "
            "Name the mechanism verb. Not 'a tool that helps teams'.\n"
            "- How it works: Name specific inputs (idea, URL, data), "
            "actions (extracts, analyzes, generates), outputs (blueprint, report, dashboard). "
            "Never 'Input your data'.\n"
            "- PROOF: Specific and grounded. Write 'add when measured' for unknown numbers — "
            "never use [bracket placeholders].\n"
            "- FINAL CTA Headline: A complete sentence. "
            "Name the specific artifact the user has after session 1. "
            "Never end with 'to' or a preposition.\n"
            "Banned words: streamline, empower, unlock, innovative, cutting-edge, revolutionize, "
            "best-in-class, game-changing, seamless, AI-powered, AI-driven, next generation, "
            "all-in-one, end-to-end, synergy, leverage, ecosystem, disrupt, robust, comprehensive, "
            "world-class, don't just take our word, you're not alone."
        )

        alt_label = f"{alt_for_prompt} {'(inferred from category)' if alt_is_inferred else ''}"

        # Pre-compute PMM analysis for direct injection into prompt
        pmm = _precompute_pmm_analysis(
            product, category, icp, core_problem, alt_for_prompt, outcome, diff
        )

        user_parts = [
            f"Build a Landing Page Blueprint for: {product}",
            f"Product is the TOOL named '{product}'. ICP is '{icp}'. Do not confuse these.",
            "",
            "=== PMM ANALYSIS (use these directly — do not re-derive or override with generic versions) ===",
            f"  Product mechanism: {pmm['product_mechanism']}",
            f"  User job: {pmm['user_job']}",
            f"  Before/After: {pmm['before_after']}",
            "  Why current options fail:",
        ]
        for alt_line in pmm["expanded_alternatives"]:
            user_parts.append(f"    - {alt_line}")

        user_parts += [
            "",
            "=== MESSAGING BRAIN ===",
            f"  Product name: {product}",
            f"  ICP / Audience: {icp or '(not specified)'}",
            f"  Core Problem: {core_problem or '(not specified)'}",
            f"  Current Alternative: {alt_label}",
            f"  Desired Outcome: {outcome or '(not specified)'}",
            f"  Category Frame: {category or '(not specified)'}",
            f"  Differentiation: {diff or '(not specified)'}",
            f"  Anti-Positioning: {anti or '(not specified)'}",
            f"  Tone: {tone or '(not specified)'}",
        ]

        if how_it_works_hint:
            user_parts += [
                "",
                "=== HOW IT WORKS HINT (use this as your starting point — adapt wording, keep concrete steps) ===",
                f"  {how_it_works_hint}",
            ]

        if proof_hint:
            user_parts += [
                "",
                "=== PROOF HINT (expand these into full product-specific suggestions — no bare brackets) ===",
                f"  {proof_hint}",
            ]

        if any([product_story, problem_story, transformation]):
            user_parts += ["", "=== NARRATIVE CONTEXT ==="]
            if product_story:
                user_parts.append(f"  Product Story: {product_story}")
            if problem_story:
                user_parts.append(f"  Problem Story: {problem_story}")
            if transformation:
                user_parts.append(f"  Transformation: {transformation}")

        if brief.examples:
            user_parts += ["", f"=== EXAMPLES / PROOF ===\n  {brief.examples}"]
        if brief.context:
            user_parts += ["", f"=== ADDITIONAL CONTEXT ===\n  {brief.context}"]

        user_parts += [
            "",
            "Write the full Blueprint now. All 7 sections required. Use ## headers. Every field value must be in double quotes on its own line after the label.",
            f"Remember: '{product}' is the product name. Never write '{icp}' as the product.",
        ]
        user = "\n".join(user_parts)

        _BLUEPRINT_REJECT_PATTERNS = (
            "[insert ", "insert image", "insert eye-catching",
            "[first step", "[second step", "[third step", "[fourth step",
            "[step ", "[describe ", "[add quote", "[add when", "[your ",
            "[specify", "[enter ", "[placeholder", "[name ", "[include ",
            "[what the user", "[action they", "[example",
            "don't just take our word",
            "not alone.", "you're not alone",
            "tbd", "to be determined", "to be added", "coming soon",
            # LLM echoing the format descriptor instead of filling content
            "what the actual proof looks like for this specific product",
            "[type] —",
            # LLM pasting the hint format instructions literally
            "use this as starting point",
            "expand on it with specific",
            "a how it works hint will be provided",
            "a proof hint will be provided",
            # Generic/awkward phrasings that indicate low-quality output
            "stop guessing",
            "was not built for",
            "were not built for",
            "is not designed for this",
            "sharper communication",
            "clear communication",
            "without the hassle",
            "take your business to the next level",
            "the old way",
            "traditional approach",
        )

        def _valid(out: str) -> bool:
            if not _validate_blueprint_output(out):
                return False
            lower = out.lower()
            if any(p in lower for p in _BLUEPRINT_REJECT_PATTERNS):
                return False
            # ## HERO must exist and contain a Headline field
            if "## hero" not in lower:
                return False
            if "headline" not in lower:
                return False
            # ## TONE + VOICE must exist and have content
            tone_idx = lower.find("## tone + voice")
            if tone_idx < 0 or len(out[tone_idx:].strip()) < 20:
                return False
            return True

        system_strict = (
            f"PMM strategist. Product: '{product}'. ICP: '{icp}'. These are different things. "
            "STRICT mode. Output Landing Page Blueprint with EXACTLY these 7 ## headers in order: "
            + ", ".join(f"## {h}" for h in _BLUEPRINT_HEADERS) + ". "
            "Every field value must be on its own line in double quotes immediately after the label. "
            "Notes field always last in each section. "
            "No preamble. No extra sections. No banned words. Output only the document."
        )

        raw = _run_with_retry(
            generate_fn=lambda: llm_generate(system=system, user=user, model="llama3:8b", temperature=0.3),
            strict_generate_fn=lambda: llm_generate(system=system_strict, user=user, model="llama3:8b", temperature=0.2),
            validator_fn=_valid,
        )
        if raw:
            result = _normalize_blueprint_output(raw)
            # Post-process: fix product naming bug if LLM used ICP as product name
            result = _fix_blueprint_product_name(result, product, icp)
            return result
        return self._write_landing_blueprint_fallback(
            brief, decisions, alt_for_prompt, how_it_works_hint
        )

    def _write_landing_blueprint_fallback(
        self,
        brief: ClientBrief,
        decisions: dict,
        alt_suggestion: str = "",
        how_it_works_hint: str = "",
    ) -> str:
        """Rule-based Landing Page Blueprint when LLM output is invalid or unavailable."""
        product      = clean_phrase(brief.product) or "the product"
        icp          = decisions.get("icp", "") or clean_phrase(brief.audience) or "your target users"
        core_problem = decisions.get("primary_problem", "") or clean_sentence(brief.pain or "The core problem is not yet described.")
        alternative  = decisions.get("current_alternative", "") or alt_suggestion or "existing tools in this space"
        diff         = decisions.get("differentiation", "") or f"built specifically for {icp.lower()}"
        outcome      = decisions.get("desired_outcome", "") or clean_phrase(brief.offer or "") or "the outcome they need"
        category_raw = decisions.get("category_frame", "") or product
        category     = _clean_category(category_raw, product, core_problem)
        tone         = (brief.tone or "direct and clear").strip()
        cta          = clean_sentence(brief.cta) if brief.cta else f"Start with {product}"

        # Use the expanded alternative (alt_suggestion) if the stored value is weak, boilerplate, or empty
        _ALT_BOILERPLATE_STARTS_FB = (
            "existing tools and manual",
            "current tools and manual",
            "existing solutions",
            "existing software",
            "not built specifically",
            "manual approaches that",
        )
        _alt_lower = alternative.strip().lower()
        _alt_words = [w.strip(".,") for w in _alt_lower.split()]
        _alt_is_weak = (
            not alternative.strip()
            or (len(_alt_words) <= 2 and all(w in _WEAK_ALT_TOKENS for w in _alt_words))
            or any(_alt_lower.startswith(p) for p in _ALT_BOILERPLATE_STARTS_FB)
        )
        if _alt_is_weak and alt_suggestion:
            alternative = alt_suggestion
        alt_first = alternative.split(",")[0].strip() if alternative else "current tools"
        icp_noun  = _icp_role_noun(icp)   # already in plural/natural form from ICP string

        # HOW IT WORKS: use hint if available, else category-derived concrete steps
        if how_it_works_hint:
            how_block = how_it_works_hint
        else:
            how_block = _infer_how_it_works(category, product, icp, outcome, diff, core_problem)
        if not how_block:
            how_block = (
                f"1. Describe your product and the problem it solves.\n"
                f"2. {product} extracts positioning — ICP, problem, differentiation.\n"
                f"3. Review and refine the decisions in the Messaging Brain.\n"
                f"4. Generate your Landing Page Blueprint."
            )

        # Proof suggestions grounded in product type
        proof_block = _infer_proof_suggestions(category, product, icp, outcome, core_problem)

        # --- Headline: short outcome statement, max 9 words ---
        # Prefer outcome over diff. Strip leading articles, trim at natural phrase boundary.
        _VERB_STARTS = (
            "starts", "predicts", "helps", "uses", "works", "gives", "generates",
            "creates", "builds", "runs", "turns", "tracks", "manages", "extracts",
        )
        # Words that, when trailing, mean the phrase was cut mid-thought
        _TRAILING_INCOMPLETE = {
            "before", "after", "because", "without", "while", "when", "if",
            "that", "which", "by", "using", "via", "through", "from", "they",
            "and", "or", "so", "but", "the", "a", "an",
        }

        def _trim_clean(words: list, max_words: int) -> str:
            """Trim to max_words and remove trailing incomplete-clause words."""
            result = words[:max_words]
            while result and result[-1].lower().rstrip(".,") in _TRAILING_INCOMPLETE:
                result = result[:-1]
            return " ".join(result).rstrip(".,")

        def _trim_to_headline(text: str, max_words: int = 9) -> str:
            words = text.split()
            if words and words[0].lower() in ("a", "an", "the"):
                words = words[1:]
            # If first word is a verb, strip it to keep the noun clause
            if words and words[0].lower() in _VERB_STARTS:
                words = words[1:]
            return _trim_clean(words, max_words)

        if outcome:
            headline = _trim_to_headline(outcome, 8)
        elif diff:
            headline = _trim_to_headline(diff, 8)
        else:
            headline = f"The {category.split()[0].lower() if category.split() else 'tool'} {icp_noun} actually need"

        # --- Subhead: "[Product] helps [icp_noun] [verb-phrase] without [alt_first]" ---
        # The subhead uses a verb-phrase after "helps X". Outcomes are often noun clauses
        # ("a landing page that...") so we detect and wrap them with "get".
        def _to_verb_phrase(text: str, max_words: int = 8) -> str:
            """Return a verb phrase suitable for 'helps X [verb_phrase]'."""
            words = text.split()
            if not words:
                return "get the outcome they need"
            first = words[0].lower().rstrip(".,")
            _EXTRA_VERBS = {"build", "reduce", "increase", "stop", "fix", "write",
                           "optimize", "identify", "improve", "analyze", "find",
                           "create", "ship", "launch", "send", "get", "reach",
                           "automate", "connect", "detect", "discover", "diagnose"}
            if first in _VERB_STARTS or first in _EXTRA_VERBS:
                # Already a verb phrase — trim and clean
                return _trim_clean(words, max_words)
            # Noun clause ("a landing page...") — prepend "get " and keep article intact
            return "get " + _trim_clean(words, max_words - 1)

        if outcome:
            mech = _to_verb_phrase(outcome, 8).lower()
        elif diff:
            mech = _to_verb_phrase(diff, 8).lower()
        else:
            mech = "get the structured outcome they need"
        subhead = f"{product} helps {icp_noun} {mech} — without {alt_first.lower()}."

        # Reinforcement line — what the user has after session 1, as a clean noun phrase
        _ALL_VERB_STARTS = set(_VERB_STARTS) | {"reduce", "build", "stop", "fix", "write", "increase", "grow", "ship"}
        if outcome:
            out_words_full = outcome.split()
            first_word = out_words_full[0].lower().rstrip(".,") if out_words_full else ""
            if first_word in _ALL_VERB_STARTS:
                # Verb-phrase outcome: wrap as "a plan to [verb phrase]"
                first_result = "a plan to " + _trim_clean(out_words_full, 6)
            else:
                # Noun-phrase outcome: use as-is, trim cleanly
                first_result = _trim_clean(out_words_full, 9)
                if first_result and first_result[0].isupper() and first_word not in ("i",):
                    first_result = first_result[0].lower() + first_result[1:]
        else:
            first_result = "a complete landing blueprint"

        # Singular icp noun for testimonial/proof labels (strip trailing 's' if plural)
        icp_singular = icp_noun.rstrip("s") if icp_noun.endswith("s") and len(icp_noun) > 3 else icp_noun
        # Ensure problem sentence ends with period for clean joining
        problem_sentence = core_problem.rstrip(".").rstrip(",") + "."

        # WHY CURRENT OPTIONS FAIL: use pre-computed failure reasons instead of generic "not built for"
        pmm = _precompute_pmm_analysis(product, category, icp, core_problem, alternative, outcome, diff)
        _why_lines = []
        for alt_line in pmm["expanded_alternatives"]:
            _why_lines.append(alt_line)
        _why_fail_block = "\n".join(_why_lines) if _why_lines else f"{alt_first} covers the broad category but does not address the specific mechanics {icp_noun} need."

        # CTA: use a human action, never stuff the product name
        if not cta or product.lower() in cta.lower():
            cta = "Try it with your product"

        return (
            f"POSITIONING SUMMARY\n"
            f"Product: {product} — {category}.\n"
            f"Audience: {icp}.\n"
            f"Problem: {core_problem}\n"
            f"Differentiation: {diff}.\n"
            "\n"
            f"HERO\n"
            f"Purpose: Establish the promise immediately and qualify the visitor.\n"
            f"Headline: {headline}\n"
            f"Subhead: {subhead}\n"
            f"Primary CTA: {cta}\n"
            f"Proof line: {icp_singular.capitalize()} quote — someone who completed their first session and shipped: [add when available].\n"
            "\n"
            f"PROBLEM SECTION\n"
            f"Purpose: Make the visitor feel understood before you explain the product.\n"
            f"{problem_sentence} The workaround most {icp_noun} reach for is {alt_first.lower()} — which adds time without closing the gap.\n"
            f"- The problem is not a lack of effort. It is the absence of a structured process.\n"
            f"- Every hour spent patching with {alt_first.lower()} is an hour not spent on the actual outcome.\n"
            "\n"
            f"WHY CURRENT OPTIONS FAIL\n"
            f"Current alternative: {alternative}\n"
            f"{_why_fail_block}\n"
            "\n"
            f"PRODUCT EXPLANATION\n"
            f"{product} is {'an' if (category or '').strip().lower()[:1] in 'aeiou' else 'a'} {category} that helps {icp_noun} {mech}.\n"
            f"10-word version: {'An' if (category or '').strip().lower()[:1] in 'aeiou' else 'A'} {(category.split()[0] if category.split() else 'focused').lower()} tool that replaces {alt_first.lower()} for {icp_noun}.\n"
            "\n"
            f"HOW IT WORKS\n"
            f"{how_block}\n"
            "\n"
            f"PROOF / CREDIBILITY\n"
            f"{proof_block}\n"
            "\n"
            f"FINAL CTA SECTION\n"
            f"CTA: {cta}\n"
            f"Reinforcement line: After one session, {icp_noun} will have {first_result} — ready to hand off or publish, without another round of {alt_first.lower()}.\n"
            "\n"
            f"UX / CONTENT NOTES\n"
            f"Headline length: max 10 words. Outcome only. No colons.\n"
            f"Tone: {tone}. Write like the person talking, not a product announcement.\n"
            f"Words to avoid: streamline, empower, all-in-one, powerful, seamless, next generation, robust.\n"
            f"Layout note: Problem section should appear above the fold or within the first scroll. "
            f"Hero CTA should repeat at the bottom after proof.\n"
            "\n"
            f"OPTIONAL FUTURE SECTIONS\n"
            f"FAQ: Add when {icp_noun} start asking the same two or three questions before signing up.\n"
            f"Comparison table: High value if {alt_first} is a named product {icp_noun} already know — call it out directly.\n"
            f"Onboarding preview: Add a short walkthrough or screenshot sequence showing the first session. Reduces hesitation.\n"
            f"Feature highlights: Defer until you know which capabilities convert — listing too early adds noise.\n"
        )

    def _write_landing_page_fallback(self, brief: ClientBrief, decisions: dict) -> str:
        """Rule-based landing template with new headers when LLM invalid or unavailable."""
        icp = decisions.get("icp", "") or clean_phrase(brief.audience) or "Your ideal customers"
        icp_lower = icp.lower().rstrip(".")
        problem = decisions.get("primary_problem", "") or clean_sentence(brief.pain or "Core problem not articulated.")
        # WHY EXISTING TOOLS FAIL must be structurally different from THE PROBLEM.
        # THE PROBLEM = the user's lived pain.
        # WHY EXISTING TOOLS FAIL = the alternative's structural flaw.
        # Never fall back to brief.pain here — that would duplicate THE PROBLEM section.
        alternative_raw = decisions.get("current_alternative", "")
        if alternative_raw:
            alt_name = alternative_raw.split(".")[0].strip()
            if len(alt_name.split()) <= 8:
                # Short name/label — build a WHY sentence around it
                why_fail = (
                    f"{alt_name} was not designed for {icp_lower}. "
                    f"It covers the broader category but lacks the specific mechanics this problem requires, "
                    f"forcing {icp_lower} to patch gaps with manual workarounds that slow outcomes."
                )
            else:
                # Long descriptive alternative — compress to one WHY sentence
                _alt_words = alt_name.split()
                _alt_label = " ".join(_alt_words[:min(4, len(_alt_words))]).rstrip(",").strip()
                why_fail = (
                    f"{_alt_label} were not built for {icp_lower} and miss "
                    f"the specific mechanics this problem requires."
                )
        else:
            why_fail = (
                f"The tools {icp_lower} rely on today were built for general-purpose use, not this specific job. "
                f"They miss the particular mechanics of the problem and force workarounds that add overhead."
            )
        outcome = decisions.get("desired_outcome", "") or clean_phrase(brief.offer) or "A clear path to the outcome that matters."
        category = decisions.get("category_frame", "") or f"{clean_phrase(brief.product) or 'Product'} for {icp}."
        diff_raw = decisions.get("differentiation", "")
        diff = (diff_raw.split(".")[0].strip() + ".") if diff_raw else f"Built specifically for {icp_lower}, not adapted from general-purpose tools."
        product = clean_phrase(brief.product) or "This product"
        cta = clean_sentence(brief.cta) if brief.cta else f"Get started with {product}."
        proof = clean_phrase(brief.examples or "") or ""
        if proof:
            proof_block = proof
        else:
            # Build a soft, product-specific adoption signal — category-aware, never generic
            _proof_haystack = f"{category.lower()} {product.lower()}"
            if any(w in _proof_haystack for w in ("messaging", "positioning", "copy", "saas", "ai ", "landing")):
                proof_block = "Founders who complete their first brief report clearer product narratives within the session."
            elif any(w in _proof_haystack for w in ("invest", "finance", "sip", "kyc", "wealth", "fintech")):
                proof_block = "First-time investors who complete onboarding start their first SIP without needing external guidance."
            elif any(w in _proof_haystack for w in ("sanctuary", "animal", "gaushala", "welfare", "cow")):
                proof_block = "Gaushala managers who use the tool report fewer missed health check records within the first month."
            else:
                _prod_short = (product or "this product")[:30]
                proof_block = f"Early users of {_prod_short} reach their first outcome without the overhead of general-purpose alternatives."
        headline_raw = f"{outcome}" if len(outcome.split()) <= 10 else " ".join(outcome.split()[:10])
        # Strip infinitive starts from outcome-derived headlines
        _INF_STARTS = (
            "to develop ", "to help ", "to simplify ", "to enable ", "to make ",
            "to build ", "to create ", "to provide ", "to give ", "to allow ",
            "to ensure ", "to support ", "to deliver ",
        )
        hl_lower = headline_raw.strip().lower()
        headline = headline_raw
        for inf in _INF_STARTS:
            if hl_lower.startswith(inf):
                # Drop the infinitive, capitalise the remainder
                remainder = headline_raw.strip()[len(inf):].strip()
                headline = remainder[:1].upper() + remainder[1:] if remainder else product
                break
        # Strip offer-description patterns ("A simple way to X", "A better way to Y")
        _OFFER_STARTS = (
            "a simple way to ", "a better way to ", "a faster way to ",
            "an easy way to ", "the easiest way to ", "a quick way to ",
        )
        _hl_words = headline.split()
        _hl_lower2 = headline.strip().lower()
        for s in _OFFER_STARTS:
            if _hl_lower2.startswith(s):
                _hl_words = []  # force domain fallback
                break
        # Strip trailing conjunctions (e.g. headline truncated mid-phrase ending with "and")
        while _hl_words and _hl_words[-1].lower().rstrip(".,") in _TRAILING_CONJ:
            _hl_words.pop()
        headline = " ".join(_hl_words)
        # Domain-aware fallback when headline is too short or was stripped entirely
        if len(headline.split()) < 3:
            _hl_domain = f"{product.lower()} {category.lower()} {outcome.lower()} {icp_lower}"
            if any(w in _hl_domain for w in ("gaushala", "sanctuary", "animal", "cow", "welfare", "shelter")):
                headline = "Manage Cow Welfare Simply"
            elif any(w in _hl_domain for w in ("invest", "finance", "sip", "kyc", "wealth", "fintech")):
                headline = "Start Investing with Confidence"
            elif any(w in _hl_domain for w in ("messaging", "positioning", "copy", "saas", "landing")):
                headline = "Turn Product Thinking into Clear Messaging"
            else:
                headline = f"Get More from {product}"
        # One clean sentence subhead: audience + pain joined with comma (not two sentences)
        _prob_first = problem.split(".")[0].rstrip(".")
        _subhead_candidate = f"For {icp_lower}, {lower_first(_prob_first)}."
        if len(_subhead_candidate.split()) <= 20:
            subhead = _subhead_candidate
        else:
            _max_prob_words = max(4, 20 - len(f"For {icp_lower},".split()) - 1)
            _prob_trimmed = " ".join(_prob_first.split()[:_max_prob_words]).rstrip(",.")
            subhead = f"For {icp_lower}, {lower_first(_prob_trimmed)}."
        # WHAT THIS IS must be category + mechanism (turns/helps/guides/tracks/manages/explains/generates/records)
        cat_lower = category.lower()
        _landing_haystack = f"{cat_lower} {product.lower()} {problem.lower()} {outcome.lower()}"
        if any(w in _landing_haystack for w in ("messaging", "positioning", "copy", "content", "launch", "saas", "ai ", "landing")):
            what_this_is = f"An AI messaging workspace that turns rough product thinking into positioning, landing copy, and UX drafts."
        elif any(w in _landing_haystack for w in ("invest", "finance", "sip", "risk", "kyc", "wealth", "fintech")):
            what_this_is = "A guided onboarding assistant that explains risk, completes KYC, and helps new investors start their first SIP."
        elif any(w in _landing_haystack for w in ("sanctuary", "shelter", "animal", "care", "rescue", "cow", "gaushala", "welfare")):
            what_this_is = "A welfare management tool that registers animals, tracks health checks, and manages sponsors."
        else:
            # Build a proper WHAT THIS IS with category + mechanism for unknown domains
            _out = (outcome or "a clear result").split(".")[0].strip().lower()[:50]
            _prob = (problem or "the core challenge").split(".")[0].strip().lower()[:50]
            what_this_is = f"A focused tool that helps {icp_lower} move from {_prob} to {_out}."
        body = f"""HEADLINE
{headline}

SUBHEADLINE
{subhead}

WHAT THIS IS
{what_this_is}

WHO IT IS FOR
{icp}

THE PROBLEM
{problem}

WHY EXISTING TOOLS FAIL
{why_fail}

HOW IT WORKS
{diff}

KEY BENEFITS
{proof_block}

CALL TO ACTION
{cta}
"""
        return (_cleanup_landing_output(body).rstrip("\n") + "\n")

    def rewrite_landing_page(self, brief: ClientBrief, draft: str, critique: dict) -> str:
        """Senior editor pass: tighten headline, compress subhead, remove repetition.

        If the draft has valid structure, runs an LLM editorial pass to sharpen it.
        Falls back to the original draft if the rewrite fails validation.
        Emergency fallback if the draft is structurally broken.
        """
        _LANDING_HEADERS = (
            "HEADLINE", "SUBHEADLINE", "WHAT THIS IS", "WHO IT IS FOR", "THE PROBLEM",
            "WHY EXISTING TOOLS FAIL", "HOW IT WORKS", "KEY BENEFITS", "CALL TO ACTION",
        )

        if not draft or not _validate_headers(draft, _LANDING_HEADERS):
            # Emergency fallback: structurally broken draft
            product = clean_phrase(brief.product) or "Your product"
            audience = clean_phrase(brief.audience) or "your audience"
            pain = clean_sentence(brief.pain or "The core problem is not yet described.")
            offer = clean_phrase(brief.offer) or "a focused solution"
            cta = clean_sentence(brief.cta) if brief.cta else f"Get started with {product}."
            return (f"HEADLINE\n{product}: {offer}\n\n"
                    f"SUBHEADLINE\nFor {audience}. {pain}\n\n"
                    f"WHAT THIS IS\n{product} helps {audience.lower()} get from {(clean_phrase(brief.pain) or 'the core problem')[:50].lower()} to {(clean_phrase(brief.offer) or 'a clear outcome')[:50].lower()}.\n\n"
                    f"WHO IT IS FOR\n{audience}\n\n"
                    f"THE PROBLEM\n{pain}\n\n"
                    f"WHY EXISTING TOOLS FAIL\n"
                    f"Current tools {audience.lower()} rely on were not built for {offer.lower()}. "
                    f"They cover the category broadly but miss the specific friction {audience.lower()} face.\n\n"
                    f"HOW IT WORKS\n{offer}.\n\n"
                    f"KEY BENEFITS\nEarly users reach {offer.lower()} without the overhead of general-purpose alternatives.\n\n"
                    f"CALL TO ACTION\n{cta}\n")

        # LLM senior editor pass: tighten and sharpen without replacing product-specific language
        editor_system = (
            "You are a senior editor tightening a product landing page. "
            "Do NOT replace product-specific language with generic templates. Do NOT add new content. "
            "Your job is to CUT, SHARPEN, and REMOVE REPETITION.\n"
            "RULES:\n"
            "1. HEADLINE: max 10 words. Outcome only. No colon. No 'to help/simplify/develop'. Cut to a sharp outcome statement.\n"
            "2. SUBHEADLINE: max 20 words. One sentence. Product + mechanism.\n"
            "3. WHAT THIS IS: must be category + mechanism (how it works). Not vague. Full sentence.\n"
            "4. WHO IT IS FOR: noun phrase only (user type). No verbs like simplify/complete/develop. If it's an action, rewrite as audience (e.g. 'First-time retail investors' not 'Simplify the process of starting a first SIP').\n"
            "5. THE PROBLEM vs WHY EXISTING TOOLS FAIL: MUST be distinct. "
            "THE PROBLEM = user's lived pain. WHY EXISTING TOOLS FAIL = the alternative's structural flaw. "
            "If they repeat, rewrite WHY to focus on the named alternative.\n"
            "6. HOW IT WORKS: 1–3 sentences. Core mechanism in plain terms. Must not repeat WHAT THIS IS.\n"
            "7. KEY BENEFITS: remove time claims, fabricated stats. Keep only believable neutral claims. 1–3 sentences.\n"
            "8. CALL TO ACTION: one line. Product-specific verb.\n"
            "9. Cross-section repetition: if a phrase appears in 2+ sections, cut it from the weaker one.\n"
            "10. Remove AI-sounding transitions: 'In today's world', 'That's where X comes in', 'But what if', "
            "'Imagine a world', 'The truth is', 'Here's the thing', 'Let's face it'.\n"
            "11. Remove filler adjectives: robust, comprehensive, unique, truly, simply, actually.\n"
            "12. Every section must have 1–3 sentences. Keep all 9 headers. Return only the revised document. No preamble."
        )
        def _rewrite_headline_ok(t: str) -> bool:
            first = _section_first_line(t, "HEADLINE", "SUBHEADLINE")
            if not first:
                return True
            words = first.split()
            if len(words) > 10 or ":" in first:
                return False
            lower = first.strip().lower()
            _INF_STARTS = (
                "to help ", "to simplify ", "to develop ", "to enable ", "to make ",
                "to build ", "to create ", "to provide ", "to give ", "to allow ",
                "to ensure ", "to support ", "to deliver ",
            )
            for bad in _INF_STARTS:
                if lower.startswith(bad):
                    return False
            return True

        def _rewrite_diff_ok(t: str) -> bool:
            what = _section_first_line(t, "WHAT THIS IS", "WHO IT IS FOR")
            how = _section_first_line(t, "HOW IT WORKS", "KEY BENEFITS")
            if not what or not how:
                return True
            w_words = set(what.lower().split())
            h_words = set(how.lower().split())
            if not w_words or not h_words:
                return True
            overlap = len(w_words & h_words) / min(len(w_words), len(h_words))
            return overlap < 0.6

        def _rewrite_subhead_ok(t: str) -> bool:
            first = _section_first_line(t, "SUBHEADLINE", "WHAT THIS IS")
            return len(first.split()) <= 20 if first else True

        def _rewrite_who_ok(t: str) -> bool:
            first = _section_first_line(t, "WHO IT IS FOR", "THE PROBLEM")
            if not first or len(first.strip()) < 5:
                return True
            lower = first.strip().lower()
            for v in ("simplify", "complete", "develop", "make ", "help ", "enable ", "empower "):
                if lower.startswith(v):
                    return False
            return True

        def _rewrite_what_this_is_ok(t: str) -> bool:
            content = _section_first_line(t, "WHAT THIS IS", "WHO IT IS FOR")
            if not content or len(content.strip()) < 20:
                return False
            lower = content.strip().lower()
            mechanism_verbs = ("turns", "helps", "guides", "tracks", "manages", "explains", "generates", "records", "creates", "builds", "completes", "registers")
            if not any(v in lower for v in mechanism_verbs):
                return False
            _WHAT_THIS_IS_BANNED = (
                "product development and marketing",
                "product development",
                "marketing for",
                "development and marketing",
                "solutions for",
                "services for",
                "platform for companies",
                "tool for companies using",
            )
            if any(b in lower for b in _WHAT_THIS_IS_BANNED):
                return False
            if re.search(r"\([^)]{3,30}\)$", content.strip()):
                return False
            if len(content.strip().split()) < 8:
                return False
            return True

        editor_user = f"Tighten and sharpen this landing page:\n\n{draft}"
        try:
            rewritten = llm_generate(system=editor_system, user=editor_user, model="llama3:8b", temperature=0.15)
            if rewritten:
                rewritten = _strip_landing_preamble(rewritten)
            if (rewritten
                    and _validate_headers(rewritten, _LANDING_HEADERS)
                    and not _contains_banned_phrases(rewritten, _LANDING_BANNED)
                    and _rewrite_headline_ok(rewritten)
                    and _rewrite_subhead_ok(rewritten)
                    and _rewrite_who_ok(rewritten)
                    and _rewrite_what_this_is_ok(rewritten)
                    and _rewrite_diff_ok(rewritten)):
                return (rewritten.rstrip("\n") + "\n")
        except Exception:
            pass

        # Editor pass failed or introduced violations — return original draft (already valid from write_landing_page)
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

    # -----------------------------------------------------------------------
    # Structured slot generators — V1 fixed-schema output for the API
    # -----------------------------------------------------------------------

    def write_landing_slots(self, brief: ClientBrief) -> dict:
        """Generate landing page copy as a fixed-schema dict.

        Returns exactly these keys (empty string if the model misses one):
          headline, subhead, problem, why_current_options_fail,
          what_this_is, primary_cta
        """
        _SCHEMA = (
            "headline", "subhead", "problem",
            "why_current_options_fail", "what_this_is", "primary_cta",
        )
        decisions = self.brain_decisions or {}
        pos = self.positioning

        product     = clean_phrase(brief.product) or "the product"
        icp         = (getattr(pos, "icp", "") if pos else "") or decisions.get("icp") or brief.audience or ""
        problem     = (getattr(pos, "core_problem", "") if pos else "") or decisions.get("primary_problem") or brief.pain or ""
        alternative = (getattr(pos, "enemy", "") if pos else "") or decisions.get("current_alternative") or ""
        diff        = (getattr(pos, "differentiation", "") if pos else "") or decisions.get("differentiation") or ""
        outcome     = (getattr(pos, "promise", "") if pos else "") or decisions.get("desired_outcome") or brief.offer or ""
        category    = (getattr(pos, "category", "") if pos else "") or decisions.get("category_frame") or ""
        anti        = (getattr(pos, "anti_positioning", "") if pos else "") or decisions.get("anti_positioning") or ""
        tone        = (brief.tone or "direct and clear").strip()

        # --- generation-time hygiene: normalise before prompt injection ---
        icp         = _strip_product_subject(_prep_ctx(icp, max_words=10), product)
        problem     = _strip_product_subject(_prep_ctx(problem, max_words=14), product)
        alternative = _prep_ctx(alternative, max_words=6)
        diff        = _prep_ctx(diff, max_words=12)
        outcome     = _prep_ctx(outcome, max_words=12)
        category    = _prep_ctx(category, max_words=8)
        anti        = _prep_ctx(anti, max_words=12)
        tone        = _prep_ctx(tone, max_words=6)

        system = (
            "You are a senior product copywriter. Respond with ONLY a valid JSON object — no markdown, no preamble.\n"
            "Keys: headline, subhead, problem, why_current_options_fail, what_this_is, primary_cta.\n\n"
            "FIELD RULES — read every rule before writing:\n"
            "- headline: ≤8 words. No colons. No question marks. No abstract nouns (clarity, efficiency, alignment, growth, success). "
            "Describe the product outcome — not the tool, not the process. "
            "Banned in headline: 'landing page copy', 'built from your brief', 'AI-powered', 'platform'. "
            "BAD: 'Unlock clarity for your team'. GOOD: 'Write positioning that converts visitors'.\n"
            "- subhead: ≤16 words. Pattern: '[Product] helps [ICP] [do specific thing] without [old frustration].' "
            "Must name the ICP and the promise. BAD: 'The best tool for modern teams'. "
            "GOOD: 'Helps early-stage founders ship landing pages without staring at a blank doc'.\n"
            "- problem: ≤14 words. Describe the exact thing that breaks — not a feeling, not 'challenges'. "
            "BAD: 'Founders struggle with messaging clarity'. GOOD: 'Founders lose visitors because their copy explains the tool, not the outcome'.\n"
            "- why_current_options_fail: ≤14 words. Name the alternative from the context directly. "
            "Explain the structural flaw — why it cannot fix the problem even if used correctly. "
            "BAD: 'Existing tools are not built specifically for this'. GOOD: 'ChatGPT writes for everyone so the output positions nothing'.\n"
            "- what_this_is: ≤14 words. Lead with the product name. State category + core mechanism simply. "
            "BAD: 'A powerful AI platform for content creation'. GOOD: 'Unimind is a positioning writer that works from a structured brief'.\n"
            "- primary_cta: 2-5 words. The literal first action the user takes. "
            "Start with a verb. Must NOT contain the product name. Must be user-facing — describe what the USER does or gets. "
            "NEVER use internal tool-building language: 'Define ICP', 'Review brief', 'Generate messaging', 'Create brain', 'Build brain', 'Generate output'. "
            "BAD: 'Sign Up', 'Get Started', 'Learn More', 'Try It Free', 'Define ICP', 'Review brief'. "
            "GOOD: 'Start your trial', 'See how it works', 'Try the workflow', 'Fix your messaging', 'Start with your idea', 'See example output'.\n\n"
            "Banned: unleash, AI-powered, AI-driven, innovative, cutting-edge, seamless, powerful solution, "
            "next-generation, game-changing, revolutionary, modern platform, all-in-one, end-to-end, robust, "
            "disruptive, transform, elevate, supercharge, streamline.\n"
            "Never use abstract nouns as subject: clarity, efficiency, alignment, growth, success, visibility.\n"
            "If a field is uncertain, write the shortest specific honest value — never marketing filler.\n"
            "The response must be a complete JSON object ending with }."
        )

        user_lines = [
            "PRODUCT BRIEF:",
            f"  Product name: {product}",
            f"  Who it is for: {icp}",
            f"  Their real pain: {problem}",
        ]
        if alternative:
            user_lines.append(f"  What they use today: {alternative}")
        if diff:
            user_lines.append(f"  Why this is different: {diff}")
        if outcome:
            user_lines.append(f"  What success looks like: {outcome}")
        if category:
            user_lines.append(f"  Category: {category}")
        if anti:
            user_lines.append(f"  What this is NOT: {anti}")
        user_lines.append(f"  Tone: {tone}")
        user_lines += [
            "",
            "EXAMPLE OUTPUT SHAPE (do NOT copy — write for the product above):",
            '{"headline": "Write positioning that converts visitors",',
            ' "subhead": "Helps early-stage founders ship landing pages without staring at a blank doc.",',
            ' "problem": "Founders lose visitors because their copy explains the tool, not the outcome.",',
            ' "why_current_options_fail": "ChatGPT writes for everyone so the output positions nothing.",',
            ' "what_this_is": "Unimind is a positioning writer that works from a structured brief.",',
            ' "primary_cta": "Start with your idea"}',
            "",
            "Return the JSON object now.",
        ]

        user = "\n".join(user_lines)
        try:
            raw = llm_generate(system=system, user=user, model="llama3:8b", temperature=0.15)
        except Exception:
            raw = ""
        slots = _extract_slots(raw, _SCHEMA)

        # Validate headline and CTA; regenerate once if either fails.
        headline_bad = not _landing_headline_ok(slots.get("headline", ""))
        cta_bad      = not _landing_cta_ok(slots.get("primary_cta", ""), product)
        if headline_bad or cta_bad:
            try:
                raw2 = llm_generate(system=system, user=user, model="llama3:8b", temperature=0.25)
            except Exception:
                raw2 = ""
            slots2 = _extract_slots(raw2, _SCHEMA)
            if headline_bad and _landing_headline_ok(slots2.get("headline", "")):
                slots["headline"] = slots2["headline"]
            if cta_bad and _landing_cta_ok(slots2.get("primary_cta", ""), product):
                slots["primary_cta"] = slots2["primary_cta"]

        return slots

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


# ---------------------------------------------------------------------------
# Generation-time context hygiene helpers
# ---------------------------------------------------------------------------

# Boilerplate strings that appear in the `context` field of profiles seeded
# from /idea before a full brief has been provided.  Blank them rather than
# let them contaminate the generation prompt.
_CTX_BOILERPLATE_FRAGMENTS: tuple[str, ...] = (
    "seeded from idea extraction",
    "run --mode brain",
    "run brain with a full brief",
)


def _prep_ctx(value: str, max_words: int = 14) -> str:
    """Normalise a single Brain field value for safe injection into a prompt.

    Rules applied in order:
    1. Blank internal boilerplate strings (e.g. the seed-profile context note).
    2. Keep only the first sentence — stops multi-idea or multi-sentence noise.
    3. Hard-cap at ``max_words`` words so long blurbs don't bias the model.
    """
    v = (value or "").strip()
    if not v:
        return ""
    # 1. Boilerplate guard
    v_lower = v.lower()
    if any(frag in v_lower for frag in _CTX_BOILERPLATE_FRAGMENTS):
        return ""
    # 2. First sentence only — stop at .!? followed by whitespace+capital or end
    m = re.search(r'[.!?](?=\s+[A-Z]|\s*$)', v)
    if m:
        v = v[:m.end()].strip()
    # 3. Word cap
    words = v.split()
    if len(words) > max_words:
        v = " ".join(words[:max_words])
    return v.strip()


def _strip_product_subject(value: str, product: str) -> str:
    """Remove the product name when it leaks in as the subject of ICP/problem fields.

    Examples:
      "Unimind helps early-stage founders..." → "Early-stage founders..."
      "Unimind is for founders who..."       → "Founders who..."
    """
    if not product or not value:
        return value
    name = re.escape(product.strip())
    patterns = (
        rf'^{name}\s+is\s+(?:a\s+|an\s+)?(?:tool\s+)?for\s+',
        rf'^{name}\s+helps?\s+',
        rf'^{name}\s+lets?\s+',
        rf'^{name}\s+enables?\s+',
        rf'^{name}\s+is\s+built\s+for\s+',
        rf'^{name}\s+was\s+built\s+for\s+',
        rf'^{name}\s+is\s+designed\s+for\s+',
    )
    for pattern in patterns:
        cleaned = re.sub(pattern, "", value, flags=re.IGNORECASE)
        if cleaned != value:
            return (cleaned[0].upper() + cleaned[1:]).strip() if cleaned else ""
    return value


# ---------------------------------------------------------------------------
# Slot-output cleanup helpers
# ---------------------------------------------------------------------------

# Fluff openers that models prepend even when instructed not to.
# Applied to non-CTA fields only so CTA verbs like "Build" are preserved.
_SLOT_FLUFF_OPENERS: tuple[str, ...] = (
    "this is a ", "this is an ", "introducing ", "meet ",
    "powered by ", "designed to ", "built to ", "created to ",
    "we help ", "we are ", "we make ", "it is a ", "it's a ",
)

# Phrases that disqualify a landing headline — trigger one retry if found.
_HEADLINE_BANNED_PHRASES: tuple[str, ...] = (
    "landing page copy",
    "built from your brief",
    "ai-powered",
    "platform",
)

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


def _landing_headline_ok(headline: str) -> bool:
    """Return True if the headline passes word-count and phrase checks."""
    h = (headline or "").lower()
    return len(headline.split()) <= 8 and not any(p in h for p in _HEADLINE_BANNED_PHRASES)


def _landing_cta_ok(cta: str, product: str) -> bool:
    """Return True if the CTA passes word-count, product-name, and internal-phrase checks."""
    if not cta:
        return False
    if len(cta.split()) > 5:
        return False
    if product and product.lower() in cta.lower():
        return False
    cta_lower = cta.lower()
    if any(phrase in cta_lower for phrase in _CTA_INTERNAL_BANNED):
        return False
    return True


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


# Per-field hard word ceilings — enforced post-generation.
_SLOT_WORD_CEILING: dict[str, int] = {
    "headline": 9,
    "subhead": 16,
    "problem": 14,
    "why_current_options_fail": 16,
    "what_this_is": 14,
    "primary_cta": 5,
    "secondary_cta": 5,
    "empty_state": 14,
    "helper_text": 14,
    "error_message": 14,
}


def _clean_slot_value(value: str, field: str) -> str:
    """Light post-generation cleanup for a single slot value.

    - Strips wrapping quotes the model sometimes adds
    - Strips known fluff openers from non-CTA fields
    - Strips trailing period from CTA fields (button labels don't end in .)
    - Trims to the field's hard word ceiling
    """
    v = (value or "").strip().strip('"\'')
    if not v:
        return ""

    # Strip fluff openers for non-CTA copy fields
    if field not in ("primary_cta", "secondary_cta"):
        v_lower = v.lower()
        for opener in _SLOT_FLUFF_OPENERS:
            if v_lower.startswith(opener):
                v = v[len(opener):].lstrip()
                v = v[0].upper() + v[1:] if v else v
                break

    # CTAs should not end with a period
    if field in ("primary_cta", "secondary_cta") and v.endswith("."):
        v = v[:-1].strip()

    # Hard word ceiling
    ceiling = _SLOT_WORD_CEILING.get(field)
    if ceiling:
        words = v.split()
        if len(words) > ceiling:
            v = " ".join(words[:ceiling])

    return v


def _extract_slots(raw: str, schema: tuple) -> dict:
    """Parse a JSON string from the LLM and normalise it to exactly the keys in schema.

    - Strips markdown fences and leading preamble
    - Returns "" for any key that is missing or not a string
    - Applies _clean_slot_value() to each result
    - Silently drops keys not in schema
    """
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text.strip())
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        data = {}
    return {
        key: _clean_slot_value(str(data.get(key) or "").strip(), key)
        for key in schema
    }


# ---------------------------------------------------------------------------
# Agent re-exports — classes moved to their own files; re-exported here so
# all existing callers (main.py, api/app.py, agent_loop.py) continue to work
# without any import changes.
# ---------------------------------------------------------------------------
from agents.critic_agent import CriticAgent  # noqa: F401


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


from agents.fact_guard_agent import FactGuardAgent  # noqa: F401


from agents.strategist_agent import StrategistAgent  # noqa: F401
