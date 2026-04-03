"""LandingPageContent — fully populated landing page sections.

The writing agent produces this from a LandingPageIA blueprint + DecisionState.
Each section carries typed copy fields so the frontend can render without
parsing markdown.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class CTAButton(BaseModel):
    """A single call-to-action button."""

    label: str = Field(description="Button text (e.g. 'Start free', 'Book a demo').")
    sub_label: Optional[str] = Field(
        default=None,
        description="Small text below the button (e.g. 'No credit card required').",
    )
    href: Optional[str] = Field(
        default=None,
        description="Destination URL. None when not yet wired to a route.",
    )
    style: str = Field(
        default="primary",
        description="Visual variant hint: 'primary', 'secondary', 'ghost'.",
    )


class LandingSection(BaseModel):
    """Fully written content for one landing page section."""

    id: str = Field(description="Matches IASection.id (e.g. 'hero', 'problem').")
    name: str = Field(description="Human-readable section name.")
    headline: Optional[str] = Field(
        default=None,
        description="Primary headline for this section.",
    )
    subheadline: Optional[str] = Field(
        default=None,
        description="Secondary headline or kicker (short line above the main headline).",
    )
    body: Optional[str] = Field(
        default=None,
        description="Main body copy. May contain markdown for paragraph breaks.",
    )
    bullets: list[str] = Field(
        default_factory=list,
        description="Bullet-point list items (features, proof points, etc.).",
    )
    cta_buttons: list[CTAButton] = Field(
        default_factory=list,
        description="CTA buttons rendered within this section.",
    )
    label: Optional[str] = Field(
        default=None,
        description="Small eyebrow label above the headline (e.g. 'For indie founders').",
    )
    social_proof_items: list[str] = Field(
        default_factory=list,
        description="Testimonial quotes, logos, or stat strings (e.g. '4.9★ on Product Hunt').",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Internal copy notes, not rendered to the user.",
    )


class LandingPageContent(BaseModel):
    """Complete written landing page content for a product."""

    client_name: str = Field(default="", description="Client slug.")
    product: str = Field(default="", description="Product name at time of generation.")
    generated_at: str = Field(default="", description="ISO 8601 UTC timestamp.")
    version: int = Field(default=1, description="Content version, incremented on regeneration.")
    ia_version: int = Field(
        default=0,
        description="Version of the LandingPageIA this content was generated from.",
    )

    sections: list[LandingSection] = Field(
        default_factory=list,
        description="Fully written sections in render order.",
    )

    page_title: Optional[str] = Field(
        default=None,
        description="HTML <title> / OG title for the page.",
    )
    meta_description: Optional[str] = Field(
        default=None,
        description="SEO meta description (under 160 chars).",
    )

    # Raw markdown fallback (populated if structured parsing fails)
    raw_markdown: Optional[str] = Field(
        default=None,
        description="Full landing page as raw markdown. Present when structured parsing fails.",
    )
