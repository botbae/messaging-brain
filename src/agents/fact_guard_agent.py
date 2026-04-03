"""FactGuardAgent — strips numeric claims not grounded in the source brief.

Moved from agents/writing_agent.py. Re-exported from there for backward compatibility.

Percentage claims (73%) and dollar figures ($1M) that appear verbatim in neither
brief.examples nor brief.context are replaced with [VERIFY: <claim>] markers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents.writing_agent import ClientBrief


@dataclass
class FactGuardAgent:
    name: str = "FactGuardAgent"

    def clean(self, text: str, brief: "ClientBrief") -> str:
        """Replace unverified numeric claims with [VERIFY: <claim>] markers.

        Source of truth: brief.examples and brief.context. Any percentage or
        dollar figure not found verbatim in either field gets a VERIFY tag.
        """
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
