"""Core text helpers used across agents."""

import re
from typing import Optional


def clean_sentence(s: Optional[str]) -> str:
    text = " ".join((s or "").split()).strip()
    if not text:
        return ""
    if text[-1] not in ".!?":
        text += "."
    return text


def clean_phrase(s: Optional[str]) -> str:
    text = " ".join((s or "").split()).strip()
    if not text:
        return ""
    for sep in [".", "!", "?"]:
        parts = [p.strip() for p in text.split(sep) if p.strip()]
        if parts:
            text = parts[0]
            break
    if text and text[-1] in ".!?":
        text = text[:-1]
    return text


def lower_first(s: str) -> str:
    if not s:
        return ""
    first, rest = s[0], s[1:]
    if "A" <= first <= "Z":
        first = first.lower()
    return first + rest



_SAFE_CLIENT_RE = re.compile(r"\w[\w-]{0,63}")


def is_safe_client_slug(slug: Optional[str]) -> bool:
    """True if slug is a plain folder name (letters, digits, - and _ only).

    Client slugs become folder names under clients/, so anything with
    slashes, dots or leading separators could escape that folder.
    """
    return bool(slug) and bool(_SAFE_CLIENT_RE.fullmatch(slug))
