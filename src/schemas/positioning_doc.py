"""PositioningDoc — structured output of the positioning generation step.

Replaces the raw markdown string produced by the positioning agent with
validated, addressable sections that can be rendered by the frontend
independently or combined into a full document.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class PositioningSection(BaseModel):
    """A single named section in the positioning document."""

    title: str = Field(description="Section heading (e.g. 'Value Proposition', 'ICP').")
    content: str = Field(description="Full section body text.")
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="How confident the agent is in this section's accuracy.",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Internal notes or caveats about this section (not for display).",
    )


class PositioningDoc(BaseModel):
    """Complete structured positioning document for a product."""

    client_name: str = Field(default="", description="Client slug this document belongs to.")
    version: int = Field(default=1, description="Document version, incremented on regeneration.")
    generated_at: str = Field(default="", description="ISO 8601 UTC timestamp.")

    # Core positioning sections
    value_proposition: Optional[PositioningSection] = Field(
        default=None,
        description="One-sentence statement of what the product does and for whom.",
    )
    icp: Optional[PositioningSection] = Field(
        default=None,
        description="Ideal Customer Profile — who this product is specifically built for.",
    )
    problem_frame: Optional[PositioningSection] = Field(
        default=None,
        description="How the product frames the problem it solves.",
    )
    differentiation: Optional[PositioningSection] = Field(
        default=None,
        description="Why this product wins against the alternatives the ICP currently uses.",
    )
    category_frame: Optional[PositioningSection] = Field(
        default=None,
        description="The category or mental model this product wants to own.",
    )
    tone_voice: Optional[PositioningSection] = Field(
        default=None,
        description="Tone, vocabulary, and communication style guidelines.",
    )
    desired_outcome: Optional[PositioningSection] = Field(
        default=None,
        description="The specific outcome the ICP achieves after using the product.",
    )

    # Catch-all for additional sections the agent may produce
    extra_sections: list[PositioningSection] = Field(
        default_factory=list,
        description="Any positioning sections not covered by the typed fields above.",
    )

    # Raw markdown fallback (populated if parsing into sections fails)
    raw_markdown: Optional[str] = Field(
        default=None,
        description="Full positioning output as raw markdown. Present when structured parsing fails.",
    )
