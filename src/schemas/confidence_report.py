"""ConfidenceReport — field-level and overall confidence scores with recommendations.

Produced by the confidence-scoring step (to be built in Phase 2).
Tells the frontend whether the brain is ready for generation, and surfaces
specific fields that need improvement before safe output can be produced.
"""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


class FieldScore(BaseModel):
    """Confidence score and recommendation for a single brain field."""

    field_name: str = Field(description="Brain or decision field name being scored.")
    score: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score from 0.0 (unusable) to 1.0 (ready).",
    )
    status: Literal["strong", "draft", "weak", "missing"] = Field(
        description=(
            "strong (≥0.8): field is specific and grounded. "
            "draft (0.5–0.79): present but needs sharpening. "
            "weak (0.2–0.49): vague, generic, or risky. "
            "missing (<0.2 or empty): absent."
        )
    )
    is_critical: bool = Field(
        default=False,
        description="True if this field blocks safe generation when weak/missing.",
    )
    value_preview: Optional[str] = Field(
        default=None,
        description="Truncated value for display (first 120 chars).",
    )
    recommendation: Optional[str] = Field(
        default=None,
        description="Actionable instruction for improving this field.",
    )
    example: Optional[str] = Field(
        default=None,
        description="Concrete example of what a strong version of this field looks like.",
    )


class ConfidenceReport(BaseModel):
    """Full confidence report for a client's brain state."""

    client_name: str = Field(default="", description="Client slug.")
    generated_at: str = Field(default="", description="ISO 8601 UTC timestamp.")
    brain_version: int = Field(
        default=0,
        description="The brain version this report was generated from.",
    )

    overall_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Weighted average confidence across all critical fields.",
    )
    generation_safe: bool = Field(
        description=(
            "True when the brain is ready to generate outputs. "
            "False when one or more critical fields are weak or missing."
        )
    )
    blocker_count: int = Field(
        default=0,
        ge=0,
        description="Number of critical fields that are weak or missing.",
    )

    field_scores: list[FieldScore] = Field(
        default_factory=list,
        description="Per-field scores, sorted by criticality then ascending score.",
    )

    summary: Optional[str] = Field(
        default=None,
        description="One-paragraph human-readable summary of the report.",
    )
    next_action: Optional[str] = Field(
        default=None,
        description="The single most impactful action the user should take to improve the brain.",
    )

    # Thresholds used when computing this report (stored for reproducibility)
    threshold_strong: float = Field(
        default=0.8,
        description="Score at or above which a field is considered 'strong'.",
    )
    threshold_draft: float = Field(
        default=0.5,
        description="Score at or above which a field is considered 'draft'.",
    )
    threshold_generation_safe: float = Field(
        default=0.65,
        description="Minimum overall_score required for generation_safe=True.",
    )
