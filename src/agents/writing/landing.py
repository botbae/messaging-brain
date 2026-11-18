"""Landing page writer: blueprint helpers, validators and LandingWriterMixin.

Split out of agents/writing_agent.py; import from there for a stable API.
"""

import re

from core.model_provider import generate as llm_generate
from core.utils import clean_phrase, clean_sentence, lower_first
from agents.writing.common import (
    ClientBrief,
    _contains_banned_phrases,
    _extract_slots,
    _prep_ctx,
    _run_with_retry,
    _section_first_line,
    _strip_product_subject,
    _validate_headers,
)
from agents.writing.ux import _CTA_INTERNAL_BANNED


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


# Phrases that disqualify a landing headline — trigger one retry if found.
_HEADLINE_BANNED_PHRASES: tuple[str, ...] = (
    "landing page copy",
    "built from your brief",
    "ai-powered",
    "platform",
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


class LandingWriterMixin:
    """Landing page, landing blueprint and landing slot generation.

    Mixed into WritingAgent; methods rely on its fields (brain_decisions,
    positioning, narrative) and may call methods from the other mixins.
    """

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
