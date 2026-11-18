"""Pydantic schemas for structured Messaging Brain artifacts.

These schemas are standalone — nothing in the existing generation flow imports
them yet. They are the foundation for Phase 2 structured output and API response
contracts.

Available schemas:
    decision_state      — enhanced ProductProfile fields with per-field confidence
    positioning_doc     — structured positioning output
    landing_page_ia     — landing page information architecture (sections + hierarchy)
    landing_page_content — fully populated landing page sections
    ux_copy_map         — structured UX microcopy by screen/state
    confidence_report   — field-level and overall confidence scores + recommendations
    artifact_bundle     — wrapper combining all generated artifacts for a client
"""

from schemas.decision_state import DecisionState, FieldConfidence
from schemas.positioning_doc import PositioningDoc, PositioningSection
from schemas.landing_page_ia import LandingPageIA, IASection
from schemas.landing_page_content import LandingPageContent, LandingSection
from schemas.ux_copy_map import UXCopyMap, UXScreen
from schemas.confidence_report import ConfidenceReport, FieldScore
from schemas.artifact_bundle import ArtifactBundle

__all__ = [
    "DecisionState",
    "FieldConfidence",
    "PositioningDoc",
    "PositioningSection",
    "LandingPageIA",
    "IASection",
    "LandingPageContent",
    "LandingSection",
    "UXCopyMap",
    "UXScreen",
    "ConfidenceReport",
    "FieldScore",
    "ArtifactBundle",
]
