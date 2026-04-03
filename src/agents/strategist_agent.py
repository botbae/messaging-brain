"""StrategistAgent — rule-based strategy suggestions for positioning and copy.

Moved from agents/writing_agent.py. Re-exported from there for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from core.utils import clean_phrase

if TYPE_CHECKING:
    from agents.writing_agent import ClientBrief


@dataclass
class StrategistAgent:
    """Strategy layer suggesting positioning and copy tweaks."""

    name: str = "StrategistAgent"

    def suggest(self, brief: "ClientBrief", draft: str, critique: Optional[dict] = None) -> dict:
        """Return positioning, clarity, CTA, and must-include suggestions.

        Args:
            brief:   ClientBrief with the product brief fields.
            draft:   The generated text to analyse.
            critique: Optional CriticAgent output (currently unused — reserved for future
                      pass-through logic).

        Returns:
            {
                positioning:      list[str],
                clarity_fixes:    list[str],
                cta_improvements: list[str],
                must_include:     list[str],
            }
        """
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
