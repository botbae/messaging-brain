"""DecisionState — enhanced ProductProfile representation with per-field confidence.

Maps to ProductProfile + DecisionDict but expressed as a validated Pydantic model
for use in API responses, confidence scoring, and structured agent output.

FieldConfidence mirrors the metadata already tracked in DecisionDict._meta,
promoting it to a first-class schema type.
"""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


class FieldConfidence(BaseModel):
    """Confidence metadata for a single brain field."""

    value: Optional[str] = Field(
        default=None,
        description="The extracted or edited field value. None when the field is missing.",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Extraction confidence from 0.0 (unknown) to 1.0 (high certainty).",
    )
    status: Literal["strong", "draft", "weak", "missing"] = Field(
        default="draft",
        description=(
            "strong: high confidence, specific value. "
            "draft: present but needs review. "
            "weak: vague, generic, or low confidence. "
            "missing: field is absent or empty."
        ),
    )
    evidence: Optional[str] = Field(
        default=None,
        description="Excerpt from the input that supports this value.",
    )
    fix_suggestion: Optional[str] = Field(
        default=None,
        description="Actionable advice for improving this field (populated when status is weak or missing).",
    )


class DecisionState(BaseModel):
    """Full brain state for a client — the authoritative positioning snapshot.

    Core fields mirror ProductProfile. field_confidence adds per-field metadata
    for confidence scoring and recommendations. Backward compatible: if
    field_confidence is absent, treat all fields as status='draft'.
    """

    # Core identity fields (mirror ProductProfile)
    product: str = Field(default="", description="Product name.")
    audience: str = Field(default="", description="Target audience / ICP.")
    problem: str = Field(default="", description="Primary pain the product solves.")
    alternatives: str = Field(default="", description="What users currently use instead.")
    advantage: str = Field(default="", description="Key differentiator over alternatives.")
    tone: str = Field(default="", description="Copy tone descriptor (e.g. 'direct', 'empathetic').")
    goal: str = Field(default="", description="Desired user outcome after using the product.")
    context: str = Field(default="", description="Additional product context or constraints.")

    # Extracted positioning decisions (mirrors ProductProfile.decisions)
    decisions: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Flat key-value map of positioning decisions extracted from the brain. "
            "Keys include: icp, primary_problem, current_alternative, differentiation, "
            "category_frame, desired_outcome, tone, etc."
        ),
    )

    # Confidence layer (new in v2)
    field_confidence: dict[str, FieldConfidence] = Field(
        default_factory=dict,
        description=(
            "Per-field confidence metadata keyed by field name. "
            "Keys can be any of the core fields or decision keys above."
        ),
    )
    overall_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Weighted average confidence across critical fields.",
    )
    generation_safe: bool = Field(
        default=False,
        description=(
            "True when overall_confidence and critical fields are strong enough "
            "to proceed with content generation without significant hallucination risk."
        ),
    )

    # Provenance (mirrors ProductProfile metadata)
    client_name: str = Field(default="", description="Client slug this state belongs to.")
    brain_version: int = Field(default=0, description="Incremented on every save.")
    last_saved_at: str = Field(default="", description="ISO 8601 UTC timestamp of last save.")
    source_idea: str = Field(default="", description="Raw idea string that seeded this state.")
