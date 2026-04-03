"""UXCopyMap — structured UX microcopy organized by screen and state.

Mirrors the output format of the UX microcopy agent but expressed as
addressable Pydantic models rather than a flat markdown document.
Each UXScreen holds all copy for a single screen or flow step.
"""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


class UXCopyState(BaseModel):
    """Copy for a single UI state within a screen (e.g. empty, loading, error)."""

    state: Literal[
        "default",
        "empty",
        "loading",
        "success",
        "error",
        "warning",
        "onboarding",
        "tooltip",
        "custom",
    ] = Field(description="The UI state this copy applies to.")

    headline: Optional[str] = Field(
        default=None,
        description="Main heading shown in this state.",
    )
    body: Optional[str] = Field(
        default=None,
        description="Supporting body copy shown in this state.",
    )
    cta_label: Optional[str] = Field(
        default=None,
        description="Primary action button label.",
    )
    secondary_label: Optional[str] = Field(
        default=None,
        description="Secondary action or dismiss label.",
    )
    toast_message: Optional[str] = Field(
        default=None,
        description="Toast / snackbar text for this state.",
    )
    aria_label: Optional[str] = Field(
        default=None,
        description="Accessibility label for the primary interactive element.",
    )
    placeholder: Optional[str] = Field(
        default=None,
        description="Input placeholder text.",
    )
    helper_text: Optional[str] = Field(
        default=None,
        description="Below-input helper or validation message.",
    )


class UXScreen(BaseModel):
    """All copy for a single screen or named flow step."""

    id: str = Field(description="Machine-readable screen ID (e.g. 'onboarding_step_1').")
    name: str = Field(description="Human-readable screen name (e.g. 'Onboarding — Step 1').")
    description: Optional[str] = Field(
        default=None,
        description="What this screen does and when the user sees it.",
    )
    states: list[UXCopyState] = Field(
        default_factory=list,
        description="Copy for each distinct UI state on this screen.",
    )
    button_labels: dict[str, str] = Field(
        default_factory=dict,
        description="All button labels keyed by action name (e.g. {'submit': 'Save brief'}).",
    )
    navigation_labels: dict[str, str] = Field(
        default_factory=dict,
        description="Navigation item labels keyed by route or id.",
    )


class UXCopyMap(BaseModel):
    """Full UX microcopy map for a product."""

    client_name: str = Field(default="", description="Client slug.")
    product: str = Field(default="", description="Product name at time of generation.")
    generated_at: str = Field(default="", description="ISO 8601 UTC timestamp.")
    version: int = Field(default=1, description="Copy map version.")
    target: Literal["operator", "product"] = Field(
        default="product",
        description=(
            "operator: copy for the Unimind CLI / operator tools. "
            "product: copy for the end-user product being built by the client."
        ),
    )

    screens: list[UXScreen] = Field(
        default_factory=list,
        description="All screens in logical flow order.",
    )

    global_labels: dict[str, str] = Field(
        default_factory=dict,
        description="Product-wide labels used across multiple screens (e.g. app name, tagline).",
    )

    raw_markdown: Optional[str] = Field(
        default=None,
        description="Full UX copy as raw markdown. Present when structured parsing fails.",
    )
