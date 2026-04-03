"""ArtifactBundle — wrapper combining all generated artifacts for a client run.

A single ArtifactBundle represents the complete output of one full generation
pipeline run. It aggregates every artifact type so the API can return one
well-typed response object and the frontend can render any combination.

All artifact fields are Optional — a bundle may contain only the artifacts
that were requested in the current run.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field

from schemas.decision_state import DecisionState
from schemas.positioning_doc import PositioningDoc
from schemas.landing_page_content import LandingPageContent
from schemas.ux_copy_map import UXCopyMap
from schemas.confidence_report import ConfidenceReport


class ArtifactMeta(BaseModel):
    """Metadata about a single artifact within the bundle."""

    artifact_type: str = Field(description="Artifact type key (e.g. 'landing_page_content').")
    version: int = Field(default=1, description="Artifact version.")
    generated_at: str = Field(default="", description="ISO 8601 UTC timestamp.")
    generation_mode: str = Field(
        default="",
        description="The --mode flag used to produce this artifact (e.g. 'landing', 'ux').",
    )
    agent_loop_used: bool = Field(
        default=False,
        description="True if AGENT_LOOP=true was active during generation.",
    )
    provider_used: str = Field(
        default="ollama",
        description="Model provider used (e.g. 'ollama', 'anthropic', 'openai', 'mixed').",
    )
    model_used: str = Field(
        default="",
        description="Primary model used for the generation step.",
    )
    output_path: Optional[str] = Field(
        default=None,
        description="Path to the saved .md artifact file (relative to project root).",
    )


class ArtifactBundle(BaseModel):
    """Complete output bundle for one client generation run."""

    client_name: str = Field(default="", description="Client slug.")
    bundle_id: str = Field(
        default="",
        description="Unique identifier for this bundle (e.g. UUID or <client>_<timestamp>).",
    )
    created_at: str = Field(default="", description="ISO 8601 UTC timestamp of bundle creation.")

    # Structured artifacts (all optional — only those generated in this run are populated)
    decision_state: Optional[DecisionState] = Field(
        default=None,
        description="Brain state snapshot used as input for this run.",
    )
    positioning_doc: Optional[PositioningDoc] = Field(
        default=None,
        description="Structured positioning document, if generated.",
    )
    landing_page_ia: Optional[dict] = Field(
        default=None,
        description="Landing page information architecture as structured JSON (sections + meta), if generated.",
    )
    landing_page_content: Optional[LandingPageContent] = Field(
        default=None,
        description="Written landing page content, if generated.",
    )
    ux_copy_map: Optional[UXCopyMap] = Field(
        default=None,
        description="UX microcopy map, if generated.",
    )
    confidence_report: Optional[ConfidenceReport] = Field(
        default=None,
        description="Brain confidence report, if generated.",
    )

    # Per-artifact metadata
    artifact_meta: list[ArtifactMeta] = Field(
        default_factory=list,
        description="Metadata entry for each artifact present in this bundle.",
    )

    # Raw markdown outputs (keyed by mode, for compatibility with existing file-based outputs)
    raw_outputs: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Raw markdown output keyed by generation mode "
            "(e.g. {'landing': '...', 'linkedin': '...'})."
        ),
    )

    # Quality layer results (populated by /generate/bundle when quality agents run)
    critic_issues: Optional[dict] = Field(
        default=None,
        description=(
            "Output of CriticAgent.review_landing_page() on the landing artifact: "
            "{score, flags, notes, include_in_output}."
        ),
    )
    recommendations: Optional[dict] = Field(
        default=None,
        description=(
            "Output of StrategistAgent.suggest() on the landing artifact: "
            "{positioning, clarity_fixes, cta_improvements, must_include}."
        ),
    )

    errors: list[str] = Field(
        default_factory=list,
        description="Non-fatal errors or warnings encountered during generation.",
    )
