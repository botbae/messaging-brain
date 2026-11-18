"""Shared helpers for every writer: header and banned-phrase checks, retry,
slot cleanup, and the ClientBrief input type.

Split out of agents/writing_agent.py; import from there for a stable API.
"""

import json
import os
import re

from dataclasses import dataclass
from typing import Callable, Optional


def _contains_banned_phrases(text: str, banned_list: tuple[str, ...]) -> bool:
    lower = (text or "").lower()
    return any(phrase in lower for phrase in banned_list)


def _validate_headers(text: str, required_headers: tuple[str, ...]) -> bool:
    t = (text or "").strip()
    return all(h in t for h in required_headers)


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


# Fluff openers that models prepend even when instructed not to.
# Applied to non-CTA fields only so CTA verbs like "Build" are preserved.
_SLOT_FLUFF_OPENERS: tuple[str, ...] = (
    "this is a ", "this is an ", "introducing ", "meet ",
    "powered by ", "designed to ", "built to ", "created to ",
    "we help ", "we are ", "we make ", "it is a ", "it's a ",
)


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
