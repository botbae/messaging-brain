"""CriticAgent — rule-based critique for writing quality and conversion clarity.

Moved from agents/writing_agent.py. Re-exported from there for backward compatibility.
All LLM calls go through core.model_provider if added in future; current implementation
is purely rule-based.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.utils import clean_phrase

if TYPE_CHECKING:
    from agents.writing_agent import ClientBrief


@dataclass
class CriticAgent:
    name: str = "CriticAgent"

    def review_landing_page(self, draft: str, brief: "ClientBrief") -> dict:
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
