"""Entry point controlling the writing workflow."""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from agent_loop import (
    run_audit_loop,
    run_audit_mode,
    run_landing_loop,
    run_launch_pack_loop,
    run_linkedin_loop,
    run_positioning_loop,
    run_ux_microcopy_loop,
)
from agents.writing_agent import ClientBrief, CriticAgent, FactGuardAgent, StrategistAgent, WritingAgent
from core.brief import build_brief_and_mode
from core.generation_context import (
    GenerationContext,
    assess_readiness,
    build_generation_context,
    context_to_brief,
)
from core.model_provider import generate as llm_generate
from core.strategy_context import (
    PositioningContext,
    NarrativeContext,
    assess_narrative_readiness,
    build_strategy_layers,
    log_strategy_context,
)
from core.client_state import init_client_state
from core.output import next_output_path, slugify
from core.utils import clean_phrase
from product_profile import DecisionDict, ProductProfile

MODEL_NAME = "llama3:8b"


def _append_strategy_block(text: str, strategy: dict) -> str:
    if not strategy:
        return text

    lines = [text.rstrip(), "", "STRATEGY (AUTO)"]
    for key in ["positioning", "clarity_fixes", "cta_improvements", "must_include"]:
        items = strategy.get(key) or []
        for item in items:
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _print_execution_banner(mode: str, client_slug: str | None, agent_loop_on: bool) -> None:
    print("====================================")
    print(f"MODE: {mode}")
    print(f"CLIENT: {client_slug or ''}")
    print(f"MODEL: {MODEL_NAME}")
    print(f"AGENT_LOOP: {str(agent_loop_on).lower()}")


def _ensure_output_artifacts(base_dir) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = base_dir / "_manifest.jsonl"
    if not manifest_path.exists():
        manifest_path.touch()


def _extract_product_name(idea_text: str, category: str = "") -> str:
    """Extract a clean product name from a free-form idea string.

    Priority:
      1. Everything before 'is a' / 'is an' in the idea text (e.g. 'Unimind is an...' -> 'Unimind')
      2. First capitalized word when idea starts with a proper noun
      3. Category-derived name
      4. First three content words after stripping filler
    Falls back to first 40 chars of category, then raw truncated idea.
    """
    text = _strip_idea_filler(idea_text)
    for sep in [" is an ", " is a ", " - ", " — "]:
        if sep.lower() in text.lower():
            idx = text.lower().index(sep.lower())
            candidate = text[:idx].strip().rstrip(".,;:")
            if candidate and len(candidate) <= 60:
                return candidate
    words = text.split()
    if words and words[0][0].isupper() and len(words[0]) >= 3:
        return words[0]
    if category:
        for sep in [" for ", " that ", " to "]:
            if sep in category:
                return category.split(sep)[0].strip()[:50]
        return category[:50]
    return " ".join(words[:3]) if words else text[:40]


# Filler openings that founders use before describing their product.
_IDEA_FILLER_PREFIXES: tuple[str, ...] = (
    "i've been thinking about ",
    "i have been thinking about ",
    "ive been thinking about ",
    "i'm building ",
    "im building ",
    "i am building ",
    "i want to build ",
    "i want to create ",
    "i'm creating ",
    "i'm working on ",
    "im working on ",
    "i am working on ",
    "we're building ",
    "we are building ",
    "we want to build ",
    "so basically ",
    "basically ",
    "something for ",
    "a tool for ",
    "a product for ",
    "an app for ",
    "it's basically ",
    "its basically ",
    "it is basically ",
    "think of it as ",
    "imagine ",
    "what if there was ",
    "what if you could ",
    "picture this ",
    "here's the idea ",
    "here is the idea ",
    "the idea is ",
    "my idea is ",
    "i'm trying to build ",
    "i'm trying to create ",
    "im trying to build ",
    "im trying to create ",
    "i am trying to build ",
    "i am trying to create ",
    "i need to build ",
    "i need to create ",
    "i need something ",
    "i want something ",
)


def _strip_idea_filler(idea_text: str) -> str:
    """Remove conversational filler prefixes from a raw idea string."""
    text = (idea_text or "").strip()
    lower = text.lower()
    for prefix in _IDEA_FILLER_PREFIXES:
        if lower.startswith(prefix):
            text = text[len(prefix):].lstrip()
            lower = text.lower()
            # Allow stripping a second layer (e.g. "basically a tool for...")
            for prefix2 in _IDEA_FILLER_PREFIXES:
                if lower.startswith(prefix2):
                    text = text[len(prefix2):].lstrip()
                    break
            break
    return text


def _slug_from_idea_extract(extract: dict) -> str:
    """Derive a product-like slug from LLM extraction results.

    Priority: category > product field > fallback.
    Returns a lowercase hyphenated string like 'retention-drop-detector'.
    Capped at 4 words to keep slugs concise.
    """
    category = (extract.get("category") or "").strip()
    product = (extract.get("product") or "").strip()

    # Prefer category — it's usually the most concise concept label
    if category:
        source = category
    elif product:
        source = _strip_idea_filler(product)
    else:
        return "product"

    # Strip filler words that make slugs verbose
    _SLUG_STOP_WORDS = {"a", "an", "the", "for", "that", "which", "and", "or", "of", "to", "with"}
    words = [w for w in source.split() if w.lower() not in _SLUG_STOP_WORDS]
    # Cap at 4 content words
    words = words[:4]
    if not words:
        return "product"

    return slugify(" ".join(words))


# Per-field keyword lists used by _idea_source_note.
# Multi-word phrases work because matching is substring-based on lowercased text.
_IDEA_NOTE_KEYWORDS: dict[str, list[str]] = {
    "icp": [
        "founders", "startups", "teams", "developers", "marketers",
        "agencies", "designers", "operators", "enterprises", "businesses",
        "solopreneurs", "freelancers", "b2b", "saas",
    ],
    "primary_problem": [
        "confused", "struggling", "unclear", "messy", "broken",
        "difficult", "hard to", "failing", "slow", "expensive",
        "frustrating", "inconsistent", "generic", "wasted", "can't explain",
    ],
    "category_frame": [
        "messaging", "positioning", "landing page", "launch", "marketing",
        "copywriting", "content", "conversion", "analytics", "automation",
        "platform", "workflow", "ux", "tool for",
    ],
    "differentiation": [
        "unlike", "instead of", "only", "structured", "specific",
        "built for", "designed for", "focused", "tailored", "from a brief",
    ],
}


def _idea_source_note(field_key: str, value: str, idea_text: str) -> str:
    """Return a short human-readable note explaining why a decision field was inferred.

    Scans the raw idea text and extracted value for per-field signal keywords.
    Returns a phrase under 15 words.  Falls back to a generic note if no
    keywords are detected.
    """
    keywords = _IDEA_NOTE_KEYWORDS.get(field_key, [])
    if not keywords:
        return "inferred from idea text"

    combined = f"{idea_text} {value}".lower()
    found = [kw for kw in keywords if kw in combined][:3]

    if not found:
        return "inferred from idea text"
    if len(found) == 1:
        return f"detected '{found[0]}' in idea"
    if len(found) == 2:
        return f"mentions {found[0]} and {found[1]}"
    return f"mentions {found[0]}, {found[1]}, and {found[2]}"


# Generic alternative phrases that signal the LLM fell back to a vague non-answer.
# When the extracted "alternative" field matches one of these, we try harder to
# infer domain-specific alternatives from the idea text and category.
_GENERIC_ALT_PHRASES: tuple[str, ...] = (
    "generic ai writing tools",
    "generic tools",
    "existing tools",
    "existing solutions",
    "manual processes",
    "current tools",
    "traditional tools",
    "manual methods",
    "various tools",
    "other tools",
    "standard tools",
    "common tools",
    "conventional tools",
    "basic tools",
    "no specific tool",
    "not specified",
    "unknown",
)

# Single-word or two-word alternatives that are too vague to be useful.
# These are abstract category nouns, not specific tools or behaviors.
_GENERIC_ALT_SINGLE_WORDS: frozenset[str] = frozenset({
    "agencies", "agency", "consultants", "consultant",
    "dashboards", "dashboard", "spreadsheets", "spreadsheet",
    "crm", "erp", "tools", "software", "apps",
    "ai", "gpt", "chatgpt",
})

# Known tool and platform names to detect when they appear in a free-form idea string.
_KNOWN_TOOL_NAMES: frozenset[str] = frozenset({
    "notion", "slack", "airtable", "hubspot", "salesforce", "quickbooks",
    "excel", "google sheets", "sheets", "looker", "tableau", "mixpanel",
    "intercom", "zendesk", "jira", "linear", "asana", "trello",
    "mailchimp", "klaviyo", "sendgrid", "stripe", "shopify", "woocommerce",
    "webflow", "figma", "miro", "zapier", "make", "n8n",
    "chatgpt", "claude", "gpt", "openai",
    "agency", "agencies", "freelancer", "freelancers", "consultant", "consultants",
    "spreadsheets", "spreadsheet", "dashboards", "dashboard",
    "email threads", "slack threads", "crm", "erp", "bi tools", "bi tool",
})

# Domain keyword → product-specific alternative examples.
# Keyed by short domain words that appear in category or idea text.
_DOMAIN_ALTERNATIVES: dict[str, str] = {
    "ecommerce":   "Shopify dashboards, Klaviyo manual flows, spreadsheet tracking, retention agencies",
    "retention":   "Klaviyo email sequences, spreadsheet cohort tracking, manual CRM follow-up, retention agencies",
    "inventory":   "spreadsheets, ERP systems, manual counts, dashboards",
    "messaging":   "ChatGPT prompts, copywriters, Notion docs, Slack threads",
    "positioning": "ChatGPT prompts, copywriters, Notion docs, messaging agencies",
    "copywriting": "freelance writers, ChatGPT prompts, Notion docs, email templates",
    "landing page":"Webflow templates, ChatGPT prompt sessions, freelance copywriters, Notion docs",
    "landing":     "Webflow templates, ChatGPT prompt sessions, freelance copywriters, Notion docs",
    "analytics":   "spreadsheets, BI tools, dashboards, Looker, consultants",
    "reporting":   "spreadsheets, manual reports, BI tools, dashboards",
    "finance":     "spreadsheets, CFO consultants, QuickBooks manual, dashboards",
    "runway":      "spreadsheets, CFO consultants, manual forecasts",
    "recruiting":  "LinkedIn manual search, ATS tools, spreadsheets, agencies",
    "hiring":      "LinkedIn, job boards, spreadsheets, agencies",
    "sales":       "CRM manual setup, spreadsheets, email follow-ups, agencies",
    "crm":         "spreadsheets, Notion, manual email, HubSpot manual setup",
    "marketing":   "ChatGPT prompts, agencies, spreadsheets, manual workflows",
    "content":     "freelance writers, ChatGPT, Notion docs, agencies",
    "social media":"manual posting, scheduling tools, agencies, ChatGPT",
    "social":      "manual posting, scheduling tools, agencies, ChatGPT",
    "ux":          "user interviews, spreadsheets, Notion docs, UX agencies",
    "operations":  "spreadsheets, manual workflows, Notion, email chains",
    "scheduling":  "email chains, spreadsheets, Calendly manual, back-and-forth",
    "support":     "email manually, Intercom manual, spreadsheets, FAQs",
    "influencer":  "DM manually, spreadsheets, agencies, brand decks",
    "creator":     "manual outreach, spreadsheets, agencies, brand decks",
    "developer":   "CLI scripts, documentation, manual processes, copy-paste",
    "devtool":     "CLI scripts, existing libraries, documentation, workarounds",
    "saas":        "spreadsheets, manual onboarding, email chains, generic tools",
}


def _scan_idea_for_tools(idea_text: str) -> list[str]:
    """Detect explicitly mentioned tool/platform names in a free-form idea string.

    Returns up to 4 matched tool names (lowercased) in the order they are
    found.  Only looks for entries in _KNOWN_TOOL_NAMES.
    """
    text_lower = idea_text.lower()
    found: list[str] = []
    for tool in sorted(_KNOWN_TOOL_NAMES):
        if len(found) >= 4:
            break
        if tool in text_lower:
            found.append(tool)
    return found


def _infer_alternatives(idea_text: str, category: str, llm_alternative: str) -> str:
    """Return the most specific alternatives inference available.

    Priority:
    1. Explicitly mentioned tools found verbatim in the idea text.
    2. LLM-extracted value — if it is not a known generic phrase.
    3. Domain-inferred alternatives from category + idea keywords.
    4. Original LLM output as last resort (may still be generic).
    """
    llm_lower = (llm_alternative or "").lower().strip()
    # Check if the LLM output is generic — either a known phrase or all-generic single words
    is_generic_llm = any(phrase in llm_lower for phrase in _GENERIC_ALT_PHRASES)
    if not is_generic_llm:
        alt_words = {w.strip(".,;") for w in llm_lower.split(",") if w.strip()}
        # If every comma-separated item is a single generic noun, it's still generic
        if alt_words and all(
            w.strip() in _GENERIC_ALT_SINGLE_WORDS
            for item in alt_words
            for w in [item.strip()]
        ):
            is_generic_llm = True

    # Priority 1: explicit tool mentions in the idea text itself
    # Only use if at least one mention is a specific tool (not just "chatgpt" alone)
    mentioned = _scan_idea_for_tools(idea_text)
    has_specific = any(m not in _GENERIC_ALT_SINGLE_WORDS for m in mentioned)
    if mentioned and has_specific:
        return ", ".join(mentioned)

    # Priority 2: keep LLM value when it's not generic
    if llm_alternative and not is_generic_llm:
        return llm_alternative

    # Priority 3: domain inference — multi-match and merge for compound domains
    combined = (category + " " + idea_text).lower()
    matched_alts: list[str] = []
    for kw, alts in _DOMAIN_ALTERNATIVES.items():
        if kw in combined:
            for alt in alts.split(", "):
                alt_stripped = alt.strip()
                if not alt_stripped:
                    continue
                # Skip if a similar alternative already exists (substring overlap)
                alt_lower = alt_stripped.lower()
                already_covered = any(
                    alt_lower in existing.lower() or existing.lower() in alt_lower
                    for existing in matched_alts
                )
                if not already_covered:
                    matched_alts.append(alt_stripped)
    if matched_alts:
        return ", ".join(matched_alts[:6])

    # Priority 4: return LLM output as-is
    return llm_alternative


# Phrases that indicate LLM-generated fluff slipped through the prompt guardrails.
# Any extracted field containing one of these is blanked rather than seeded with garbage.
_IDEA_FLUFF_PHRASES: tuple[str, ...] = (
    "unleash", "ai-driven", "innovative platform", "cutting-edge",
    "seamless experience", "powerful solution", "next-generation",
    "next generation", "game-changing", "state-of-the-art",
    "robust platform", "leverage synerg", "all-in-one", "end-to-end",
    "modern platform", "revolutionize", "disrupt",
)


def _clean_idea_field(value: str) -> str:
    """Light normalization for a single LLM-extracted idea field.

    - Strips whitespace
    - Returns "" for placeholder-looking values ("[...]", "N/A", "TBD")
    - Returns "" if the value contains a known fluff phrase (safety net —
      the prompt bans these, but small models slip up)
    - Truncates to 150 chars at a word boundary
    """
    v = (value or "").strip()
    if not v:
        return ""
    if v.startswith("[") or v.lower() in ("n/a", "none", "tbd", "unknown", "to be determined"):
        return ""
    v_lower = v.lower()
    if any(f in v_lower for f in _IDEA_FLUFF_PHRASES):
        return ""
    if len(v) > 150:
        v = v[:150].rsplit(" ", 1)[0]
    return v


def _idea_to_profile(extract: dict, idea_text: str, client_slug: str | None = None) -> "ProductProfile":
    """Convert raw idea extraction output to an initial ProductProfile (Messaging Brain seed).

    Fields that need a full brief (current_alternative, desired_outcome, anti_positioning)
    are left blank — run --mode brain with a full brief to fill them in.
    """
    decisions = DecisionDict()
    # LLM-extracted core positioning fields — normalize then store with provenance.
    # confidence=0.7: single-pass LLM inference, not yet validated against a full brief.
    for _key, _raw in (
        ("icp",            extract.get("icp", "")),
        ("primary_problem", extract.get("problem", "")),
        ("category_frame", extract.get("category", "")),
        ("differentiation", extract.get("differentiation", "")),
    ):
        _val = _clean_idea_field(_raw)
        decisions.set_entry(
            _key, _val,
            confidence=0.7,
            source_notes=_idea_source_note(_key, _val, idea_text),
        )
    # Newly extracted optional fields — seed when present, leave blank otherwise.
    for _key, _raw in (
        ("current_alternative", extract.get("alternative", "")),
        ("desired_outcome",     extract.get("goal", "")),
    ):
        _val = _clean_idea_field(_raw)
        if _val:
            decisions.set_entry(_key, _val, confidence=0.7,
                                source_notes=_idea_source_note(_key, _val, idea_text))
        else:
            decisions[_key] = ""
    decisions["anti_positioning"] = ""

    # Prefer the LLM-extracted product field (already cleaned/resolved in _run_idea_mode).
    # Only fall back to raw idea parsing when the LLM field is empty.
    product_name = _clean_idea_field(extract.get("product", ""))
    if not product_name:
        product_name = _extract_product_name(idea_text, category=extract.get("category", ""))
    return ProductProfile(
        product=product_name,
        audience=_clean_idea_field(extract.get("icp", "")),
        problem=_clean_idea_field(extract.get("problem", "")),
        alternatives=_clean_idea_field(extract.get("alternative", "")),
        advantage=_clean_idea_field(extract.get("differentiation", "")),
        tone=_clean_idea_field(extract.get("tone", "")),
        goal=_clean_idea_field(extract.get("goal", "")),
        context="Seeded from idea extraction. Run --mode brain with a full brief to refine.",
        decisions=decisions,
        source_idea=idea_text.strip()[:200] if idea_text else "",
        client_name=client_slug or "",
    )


def _load_profile_if_exists(client_slug: str | None) -> "ProductProfile | None":
    """Load the full ProductProfile from clients/<client>/product_profile.json if it exists."""
    if not client_slug:
        return None
    profile_path = Path("clients") / client_slug / "product_profile.json"
    if not profile_path.exists():
        return None
    return ProductProfile.load(profile_path)


def _load_brain_if_exists(client_slug: str | None) -> dict | None:
    """Load positioning decisions from clients/<client>/product_profile.json if it exists.

    Returns the decisions dict (non-empty), or None if not found.
    """
    profile = _load_profile_if_exists(client_slug)
    if profile and profile.decisions:
        return profile.decisions
    return None


def _recover_json_object(raw: str) -> str:
    """Best-effort repair of common LLM JSON issues.

    Handles:
    - Extra text before/after the JSON object
    - Missing closing brace
    - Trailing commas before closing brace
    """
    import re as _re
    # Extract the first {...} block (greedy, so we get the outermost one)
    start = raw.find("{")
    if start == -1:
        return raw
    end = raw.rfind("}")
    if end == -1:
        # No closing brace — find the last real value and close it
        candidate = raw[start:].rstrip()
        # Remove trailing comma if present
        candidate = _re.sub(r",\s*$", "", candidate)
        candidate = candidate + "\n}"
    else:
        candidate = raw[start : end + 1]
    # Remove trailing commas before closing brace: {"a": "b",} -> {"a": "b"}
    candidate = _re.sub(r",\s*}", "}", candidate)
    return candidate


def _invalidate_stale_brief(client_slug: str, profile: ProductProfile) -> None:
    """When brain has been updated to a new product, invalidate the old brief.json.

    Renames clients/<client>/brief.json -> brief.json.stale so it cannot leak
    into generation, but is preserved for recovery.
    """
    brief_path = Path("clients") / client_slug / "brief.json"
    if not brief_path.exists():
        return
    stale_path = brief_path.with_suffix(".json.stale")
    brief_path.rename(stale_path)
    print(f"Stale brief invalidated: {brief_path} -> {stale_path}")
    print(f"  Reason: brain product is '{profile.product}', brief was for a different product.")
    print(f"  To restore, rename {stale_path} back to {brief_path}")


def _run_idea_mode(idea_text: str, client_slug: str | None = None) -> tuple[dict | None, Path | None]:
    """Extract ICP, problem, category, differentiation from a product idea string.

    If --client is provided:
      - Saves the raw extract to clients/<client>/idea_extract.json
      - Creates an initial product_profile.json (Messaging Brain seed)
      - Invalidates any existing brief.json that refers to a different product
      - Run --mode brain with a full brief to refine the brain further

    Returns (result_dict, profile_path) or (None, None) on failure.
    """
    import re
    system = (
        "You are a product positioning analyst. Extract positioning facts from a raw founder idea.\n"
        "Respond with ONLY a JSON object — no markdown, no explanation, no trailing text.\n"
        "Use exactly these eight keys: product, icp, problem, category, differentiation, alternative, tone, goal.\n\n"
        "Rules per field:\n"
        "- product: a concise one-line description of what is being built. Max 12 words. "
        "Describe the thing itself, not its category. Start with the mechanism or noun (e.g. 'Slack bot that...', "
        "'Runway monitoring tool that...', 'Chrome extension that...'). "
        "No generic words like 'platform', 'solution', 'ecosystem'. Always return something.\n"
        "- icp: who it is built for. Max 8 words. Name the person type specifically, not 'users' or 'people'.\n"
        "- problem: the core pain. Max 12 words. Be specific — name what breaks, not just 'lack of clarity'.\n"
        "- category: 3-6 words naming the product type. No 'platform', 'solution', 'ecosystem', 'tool'.\n"
        "- differentiation: what makes it different. Max 12 words. Start with a verb.\n"
        "- alternative: what the user currently uses instead. "
        "If the idea mentions specific tools, workflows, platforms, or services by name, list those. "
        "Otherwise infer from the domain: e-commerce → 'spreadsheets, CRM tools, agencies'; "
        "messaging/positioning → 'ChatGPT prompts, copywriters, Notion docs'; "
        "analytics → 'dashboards, spreadsheets, BI tools, consultants'. "
        "Comma-separated, 2-6 items. Each must be a named tool, specific workflow, or described behavior — "
        "never an abstract category noun like 'AI tools', 'dashboards', or 'agencies' by itself. "
        "Never write 'generic tools', 'existing solutions', or 'manual processes'.\n"
        "- tone: 2-4 words describing the voice. E.g. 'direct and strategic' or 'warm and practical'.\n"
        "- goal: the user's desired outcome. Max 10 words. Start with a verb.\n\n"
        "Never use: 'unleash', 'AI-driven', 'innovative', 'cutting-edge', 'seamless', "
        "'powerful solution', 'next-generation', 'game-changing', 'robust', 'leverage', "
        "'revolutionize', 'disrupt', 'all-in-one', 'end-to-end', 'modern platform'.\n"
        "If a field is genuinely unknown, write a short grounded guess — never a vague filler phrase.\n"
        "The response must be a complete, valid JSON object ending with }."
    )
    user = (
        f"Product idea: {idea_text}\n\n"
        "Return JSON with exactly these keys: product, icp, problem, category, differentiation, alternative, tone, goal.\n"
        "Example:\n"
        '{"product": "Positioning writer that generates landing pages from a structured brief", '
        '"icp": "early-stage SaaS founders", '
        '"problem": "can\'t explain their product clearly to visitors", '
        '"category": "positioning writer for founders", '
        '"differentiation": "works from a structured brief, not open prompts", '
        '"alternative": "ChatGPT prompt sessions, freelance copywriters, Notion docs", '
        '"tone": "direct and strategic", '
        '"goal": "ship a landing page that converts"}'
    )
    try:
        raw = llm_generate(system=system, user=user, model=MODEL_NAME, temperature=0.2)
    except Exception as e:
        print(f"Idea extraction failed: {e}")
        return None, None
    if not raw or not raw.strip():
        print("No response from model.")
        return None, None
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```\w*\n?", "", raw)
        raw = re.sub(r"\n?```\s*$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        recovered = _recover_json_object(raw)
        try:
            data = json.loads(recovered)
        except json.JSONDecodeError:
            print("Could not parse JSON after recovery attempt.\nRaw output:\n", raw)
            return None, None
    _raw_product = _clean_idea_field((data.get("product") or "").strip())
    if not _raw_product:
        # Fallback: <category> + "tool for" + <icp>, or _extract_product_name as last resort
        _fb_category = _clean_idea_field((data.get("category") or "").strip())
        _fb_icp = _clean_idea_field((data.get("icp") or "").strip())
        if _fb_category and _fb_icp:
            _raw_product = f"{_fb_category} tool for {_fb_icp}"
            _words = _raw_product.split()
            if len(_words) > 12:
                _raw_product = " ".join(_words[:12])
        else:
            _raw_product = _extract_product_name(idea_text, category=_fb_category)
    _raw_category = (data.get("category") or "").strip()
    _raw_alternative = (data.get("alternative") or "").strip()
    result = {
        "product": _raw_product,
        "icp": (data.get("icp") or "").strip(),
        "problem": (data.get("problem") or "").strip(),
        "category": _raw_category,
        "differentiation": (data.get("differentiation") or "").strip(),
        # Infer domain-specific alternatives when LLM returns a generic fallback
        "alternative": _infer_alternatives(idea_text, _raw_category, _raw_alternative),
        "tone": (data.get("tone") or "").strip(),
        "goal": (data.get("goal") or "").strip(),
    }
    # Derive a product-like slug from the extraction (not from the raw idea opening)
    result["suggested_slug"] = _slug_from_idea_extract(result)

    print("\n--- IDEA EXTRACTION ---\n")
    print(json.dumps(result, indent=2))
    print("\n--- END ---\n")

    profile_path = None
    if client_slug:
        client_dir = Path("clients") / client_slug
        client_dir.mkdir(parents=True, exist_ok=True)

        extract_path = client_dir / "idea_extract.json"
        with open(extract_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"Saved idea extract: {extract_path}")

        profile = _idea_to_profile(result, idea_text, client_slug=client_slug)
        profile_path = client_dir / "product_profile.json"

        # Check if existing brief.json refers to a different product
        # and invalidate it to prevent cross-product contamination
        old_brief_path = client_dir / "brief.json"
        if old_brief_path.exists():
            try:
                with open(old_brief_path, encoding="utf-8") as f:
                    old_brief = json.load(f)
                old_product = (old_brief.get("product") or "").strip().lower()
                new_product = (profile.product or "").strip().lower()
                if old_product and new_product and old_product != new_product:
                    # Check if they're clearly different
                    old_words = set(old_product.split())
                    new_words = set(new_product.split())
                    if not (old_words & new_words):
                        _invalidate_stale_brief(client_slug, profile)
            except Exception:
                pass  # brief.json is malformed — will be caught elsewhere

        profile.save(profile_path)
        print(f"Created initial brain: {profile_path}")
        print("Run --mode brain with a full brief to refine the brain.")

    return result, profile_path


def _run_brain_mode(brief, client_slug: str | None) -> tuple["ProductProfile", Path]:
    """Load brief, extract positioning decisions, save to product_profile.json; print result.

    Returns (profile, profile_path).
    """
    agent = WritingAgent()
    decisions = agent.extract_positioning_decisions(brief)
    profile = ProductProfile(
        product=clean_phrase(brief.product) or "",
        audience=(decisions.get("icp") or clean_phrase(brief.audience) or "").strip(),
        problem=(brief.pain or "").strip(),
        alternatives=(decisions.get("current_alternative") or "").strip(),
        advantage=clean_phrase(brief.offer) or "",
        tone=(brief.tone or "").strip(),
        goal=(decisions.get("desired_outcome") or "").strip(),
        context=(brief.context or "").strip(),
        decisions=decisions,
        source_idea="",
        client_name=client_slug or "",
    )
    client_dir = client_slug or slugify(brief.product or "product")
    profile_path = Path("clients") / client_dir / "product_profile.json"
    profile.save(profile_path)
    print(f"Saved: {profile_path}")
    print("\n--- BRAIN (product_profile) ---\n")
    print(json.dumps(profile.to_dict(), indent=2))
    print("\n--- END ---\n")
    return profile, profile_path


def _run_generate(
    brief,
    mode: str,
    client_slug: str | None,
    brain: dict | None = None,
    agent_loop_on: bool = False,
    show_strategy: bool = False,
    brief_path_used: Path | None = None,
    positioning: PositioningContext | None = None,
    narrative: NarrativeContext | None = None,
) -> tuple[str, Path, Path]:
    """Dispatch to the correct agent, save output files, and return (final_text, out_path, latest_path)."""
    agent = WritingAgent()
    if brain:
        agent.brain_decisions = brain
    if positioning:
        agent.positioning = positioning
    if narrative:
        agent.narrative = narrative

    if not agent_loop_on:
        if mode == "landing":
            final_text = agent.write_landing_blueprint(brief)
            strategy = None
        elif mode == "linkedin":
            final_text = agent.write_linkedin_post(brief)
            strategy = None
        elif mode == "ux_microcopy":
            final_text = agent.write_ux_microcopy(brief)
            strategy = None
        elif mode == "launch_pack":
            final_text = agent.write_launch_pack(brief)
            strategy = None
        elif mode == "audit":
            final_text = run_audit_mode(brief)
            strategy = None
        elif mode == "positioning":
            final_text = agent.write_positioning(brief)
            strategy = None
        elif mode == "ux":
            final_text = agent.write_ux_pack(brief, target="product")
            strategy = None
        elif mode == "ux_operator":
            final_text = agent.write_ux_pack(brief, target="operator")
            strategy = None
        elif mode == "ux_product":
            final_text = agent.write_ux_pack(brief, target="product")
            strategy = None
        else:
            final_text = agent.write_landing_page(brief)
            strategy = None
    else:
        strategist = StrategistAgent()
        if mode == "landing":
            # Blueprint replaces the loop — no critic/rewrite cycle needed
            final_text = agent.write_landing_blueprint(brief)
            strategy = None
        elif mode == "linkedin":
            final_text, meta = run_linkedin_loop(brief, agent, strategist)
            strategy = meta.get("strategy")
        elif mode == "ux_microcopy":
            final_text, meta = run_ux_microcopy_loop(brief, agent, strategist)
            strategy = meta.get("strategy")
        elif mode == "launch_pack":
            final_text, meta = run_launch_pack_loop(brief, agent, strategist)
            strategy = meta.get("strategy")
        elif mode == "audit":
            critic = CriticAgent()
            final_text, meta = run_audit_loop(brief, critic)
            strategy = meta.get("strategy")
        elif mode == "positioning":
            final_text, meta = run_positioning_loop(brief, agent)
            strategy = meta.get("strategy")
        elif mode in ("ux", "ux_product"):
            final_text = agent.write_ux_pack(brief, target="product")
            strategy = None
        elif mode == "ux_operator":
            final_text = agent.write_ux_pack(brief, target="operator")
            strategy = None
        else:
            critic = CriticAgent()
            final_text, meta = run_landing_loop(brief, agent, critic, strategist)
            strategy = meta.get("strategy")

    if show_strategy and strategy:
        final_text = _append_strategy_block(final_text, strategy)

    final_text = FactGuardAgent().clean(final_text, brief)
    final_text = final_text.rstrip("\n") + "\n"

    out_path = next_output_path(brief.product, mode, client_slug)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(final_text)

    base_dir = out_path.parent
    _ensure_output_artifacts(base_dir)
    latest_path = base_dir / f"{mode}_latest.md"
    with open(latest_path, "w", encoding="utf-8") as f:
        f.write(final_text)

    manifest_path = base_dir / "_manifest.jsonl"
    manifest_entry = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "client": client_slug or "",
        "mode": mode,
        "brief_path": str(brief_path_used) if brief_path_used is not None else "",
        "output_path": str(out_path),
        "latest_path": str(latest_path),
        "model_used": MODEL_NAME,
        "agent_loop": agent_loop_on,
    }
    with open(manifest_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(manifest_entry) + "\n")

    return final_text, out_path, latest_path


# ---------------------------------------------------------------------------
# Debug / integrity helpers
# ---------------------------------------------------------------------------

def _print_resolved_context(
    client: str | None,
    gen_ctx: "GenerationContext",
    brain_path: Path | None,
    brief_path: Path | None,
    profile: "ProductProfile | None",
) -> None:
    """Print resolved generation context before generation begins (source per field, mismatch status)."""
    src = gen_ctx.sources
    print("\n--- RESOLVED GENERATION CONTEXT ---")
    print(f"  Client:       {client or '(anonymous)'}")
    print(f"  Product:      {gen_ctx.product or '(empty)'}  (source: {src.get('product', '?')})")
    print(f"  Audience:     {gen_ctx.audience or '(empty)'}  (source: {src.get('audience', '?')})")
    print(f"  Pain:         {gen_ctx.pain or '(empty)'}  (source: {src.get('pain', '?')})")
    print(f"  Offer:        {gen_ctx.offer or '(empty)'}  (source: {src.get('offer', '?')})")
    print(f"  Tone:         {gen_ctx.tone or '(empty)'}  (source: {src.get('tone', '?')})")
    print(f"  CTA:          {gen_ctx.cta or '(empty)'}  (source: {src.get('cta', '?')})")
    print(f"  Brain:        {brain_path or '(none)'}")
    print(f"  Brief:        {brief_path or '(none)'}")
    if profile:
        print(f"  Profile updated_at:    {profile.updated_at or '(not set)'}")
        print(f"  Profile fingerprint:   {profile.product_fingerprint or '(not set)'}")
        print(f"  Profile source_idea:   {(profile.source_idea or '(not set)')[:80]}")
    if gen_ctx.cross_product_detected:
        print(f"  *** CROSS-PRODUCT: YES — brief-only fields suppressed ***")
        for note in gen_ctx.coherence_notes:
            print(f"    {note}")
    else:
        print(f"  Cross-product: no")
    print("--- END CONTEXT ---\n")


def _check_client_integrity(
    client_slug: str,
    gen_ctx: "GenerationContext",
    profile: "ProductProfile | None",
) -> None:
    """Fail loudly if client state is inconsistent and cannot be auto-repaired.

    The generation_context builder already suppresses brief-only fields when
    cross-product is detected. This function enforces the hard invariants:
    - Brain file must be loadable if it exists
    - If cross-product is detected AND brain has no core data, we cannot proceed
    """
    client_dir = Path("clients") / client_slug
    brain_path = client_dir / "product_profile.json"

    # If client directory has a brain file but it wasn't loaded, something is wrong
    if brain_path.exists() and not profile:
        print(f"FATAL: Client '{client_slug}' has a brain at {brain_path} but it could not be loaded.")
        print("Check the file for JSON errors. Aborting.")
        sys.exit(1)

    # If cross-product was detected, warn clearly (brief fields already suppressed)
    if gen_ctx.cross_product_detected:
        print("WARNING: Brief and brain refer to different products.")
        print("Brief-only fields (tone, cta, examples, context) have been suppressed.")
        print("Generation will use brain as the sole source of truth.")
        print("To fix: update brief.json to match the current product, or re-run --mode idea.\n")

    # If no product at all after merge, fail
    if not (gen_ctx.product or "").strip():
        print(f"FATAL: No product resolved for client '{client_slug}'.")
        print("Run --mode idea or provide a brief with a product field. Aborting.")
        sys.exit(1)


def run() -> None:
    brief, mode, client_slug, brief_path_used, idea_text, reset_brief = build_brief_and_mode()

    # Client init/reset: no brief or generation needed
    if mode == "init_client":
        if not client_slug:
            print("--mode init_client requires --client <name>")
            sys.exit(1)
        result = init_client_state(client_slug, reset_brief=reset_brief)
        if result.get("error"):
            print(result["error"])
            sys.exit(1)
        print(f"Client '{client_slug}' initialized.")
        if result.get("brain_removed"):
            print("  - product_profile.json removed")
        if result.get("idea_extract_removed"):
            print("  - idea_extract.json removed")
        if result.get("outputs_cleared"):
            print("  - outputs/ cleared")
        if result.get("brief_invalidated"):
            print("  - brief.json invalidated (renamed to brief.json.stale)")
        print("Next: run --mode idea --idea \"...\" --client " + client_slug + " then --mode brain --brief clients/" + client_slug + "/brief.json --client " + client_slug)
        return

    if mode == "idea":
        if not idea_text:
            print("--mode idea requires --idea <text>")
            sys.exit(1)
        _print_execution_banner(mode, client_slug, False)
        _run_idea_mode(idea_text, client_slug=client_slug)
        return

    if mode == "brain":
        _print_execution_banner(mode, client_slug, False)
        _run_brain_mode(brief, client_slug)
        return

    # Build generation context: merges brain + brief with clear priority.
    # Overrides > Brain > Brief. Cross-product detection suppresses stale brief fields.
    profile = _load_profile_if_exists(client_slug)
    gen_ctx = build_generation_context(brief=brief, profile=profile)
    brain = gen_ctx.decisions if gen_ctx.decisions else None
    # Replace brief with merged version so generators get the right data
    brief = context_to_brief(gen_ctx)

    # --- Debug print: always show resolved context ---
    if client_slug:
        brain_path = Path("clients") / client_slug / "product_profile.json"
        brief_path_client = Path("clients") / client_slug / "brief.json"
        _print_resolved_context(
            client=client_slug,
            gen_ctx=gen_ctx,
            brain_path=brain_path if brain_path.exists() else None,
            brief_path=brief_path_client if brief_path_client.exists() else None,
            profile=profile,
        )
        _check_client_integrity(client_slug, gen_ctx, profile)
    else:
        _print_resolved_context(
            client=None,
            gen_ctx=gen_ctx,
            brain_path=None,
            brief_path=brief_path_used,
            profile=profile,
        )

    if brain:
        print(f"Brain loaded: clients/{client_slug}/product_profile.json")
        print(f"Context sources: {gen_ctx.sources}")

    # Build strategy layers: positioning + narrative
    positioning, narrative = build_strategy_layers(gen_ctx)
    log_strategy_context(positioning, narrative)
    print(f"Positioning: {positioning.filled_count()}/7 fields | Narrative: {narrative.filled_count()}/5 fields")

    # Readiness check: warn if missing required fields
    readiness = assess_readiness(gen_ctx, mode)
    if not readiness.ready:
        print(f"\nWARNING: {readiness.message}")
        print("Proceeding with available data — output quality may be limited.\n")
    elif readiness.message:
        print(f"\nNOTE: {readiness.message}\n")

    # Narrative readiness check
    nar_readiness = assess_narrative_readiness(positioning, narrative, mode)
    if not nar_readiness.ready:
        print(f"\nNARRATIVE WARNING: {nar_readiness.message}\n")

    agent_loop_on = os.getenv("AGENT_LOOP", "").lower() == "true"
    show_strategy = os.getenv("SHOW_STRATEGY", "").lower() == "true"
    _print_execution_banner(mode, client_slug, agent_loop_on)

    final_text, out_path, latest_path = _run_generate(
        brief, mode, client_slug,
        brain=brain,
        agent_loop_on=agent_loop_on,
        show_strategy=show_strategy,
        brief_path_used=brief_path_used,
        positioning=positioning,
        narrative=narrative,
    )

    if brief_path_used is not None:
        print(f"Brief: {brief_path_used}")
    print(f"Saved versioned file: {out_path}")
    print(f"Updated latest file: {latest_path}")
    print("Manifest appended.")
    print(f"Output: {out_path}")
    print(f"Latest: {latest_path}")

    open_latest = os.getenv("OPEN_LATEST", "").lower() == "true"
    if open_latest and sys.platform == "darwin":
        subprocess.run(["open", str(latest_path)], check=False)

    print("\n--- GENERATED OUTPUT ---\n")
    print(final_text)
    print("\n--- END OUTPUT ---\n")

if __name__ == "__main__":
    run()
