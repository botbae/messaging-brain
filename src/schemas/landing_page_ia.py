"""LandingPageIA — Information Architecture schema for a landing page.

Represents the structural blueprint (section names, order, purpose, key messages)
before content is written. The structuring agent produces this; the writing agent
consumes it to generate LandingPageContent.
"""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


class IASection(BaseModel):
    """A single section in the landing page architecture."""

    id: str = Field(
        description="Machine-readable identifier (e.g. 'hero', 'problem', 'social_proof').",
    )
    name: str = Field(
        description="Human-readable section name (e.g. 'Hero', 'Problem Statement').",
    )
    purpose: str = Field(
        description="What this section must accomplish for the visitor.",
    )
    position: int = Field(
        description="Render order (1 = first section, top of page).",
        ge=1,
    )
    required: bool = Field(
        default=True,
        description="False for optional sections that depend on available content.",
    )
    key_message: Optional[str] = Field(
        default=None,
        description="The single most important idea this section should communicate.",
    )
    content_notes: Optional[str] = Field(
        default=None,
        description="Guidance for the writing agent (tone cues, what to avoid, etc.).",
    )
    estimated_word_count: Optional[int] = Field(
        default=None,
        description="Approximate target word count for this section.",
        ge=0,
    )
    section_type: Literal[
        "hero",
        "problem",
        "solution",
        "features",
        "social_proof",
        "cta",
        "faq",
        "pricing",
        "footer",
        "custom",
    ] = Field(
        default="custom",
        description="Canonical section type label for frontend rendering hints.",
    )


class LandingPageIA(BaseModel):
    """Full information architecture for a landing page."""

    client_name: str = Field(default="", description="Client slug.")
    product: str = Field(default="", description="Product name at time of IA generation.")
    generated_at: str = Field(default="", description="ISO 8601 UTC timestamp.")
    version: int = Field(default=1, description="IA version, incremented on regeneration.")

    sections: list[IASection] = Field(
        default_factory=list,
        description="Ordered list of sections (sorted by IASection.position).",
    )

    strategic_notes: Optional[str] = Field(
        default=None,
        description="Overall page strategy notes from the structuring agent.",
    )
    total_estimated_words: Optional[int] = Field(
        default=None,
        description="Sum of estimated_word_count across all sections.",
        ge=0,
    )
