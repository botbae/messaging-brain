"""WritingAgent: the single entry point for every generated output.

The actual writers live in agents/writing/, one module per output type:

    agents/writing/common.py       shared checks, retry, slot cleanup, ClientBrief
    agents/writing/landing.py      landing page + landing blueprint + landing slots
    agents/writing/linkedin.py     LinkedIn post
    agents/writing/ux.py           UX microcopy, UX pack, UX slots
    agents/writing/launch_pack.py  launch pack
    agents/writing/positioning.py  positioning decisions + positioning document
    agents/writing/grounding.py    GroundingAgent

WritingAgent combines them, so callers keep using:

    from agents.writing_agent import ClientBrief, WritingAgent
"""

from dataclasses import dataclass
from typing import Optional

from agents.writing.common import (  # noqa: F401
    ClientBrief,
    _clean_slot_value,
    _contains_banned_phrases,
    _CTX_BOILERPLATE_FRAGMENTS,
    _extract_slots,
    _prep_ctx,
    _print_decisions_if_debug,
    _run_with_retry,
    _section_first_line,
    _SLOT_FLUFF_OPENERS,
    _SLOT_WORD_CEILING,
    _strip_product_subject,
    _validate_headers,
)
from agents.writing.landing import (  # noqa: F401
    LandingWriterMixin,
    _ALT_BEHAVIOR_MAP,
    _BLUEPRINT_BANNED,
    _BLUEPRINT_HEADERS,
    _blueprint_section_text,
    _clean_category,
    _cleanup_landing_output,
    _expand_alternatives,
    _fix_blueprint_product_name,
    _HEADLINE_BANNED_PHRASES,
    _icp_role_noun,
    _ICP_SKIP_ENDINGS,
    _infer_how_it_works,
    _infer_proof_suggestions,
    _LANDING_BANNED,
    _landing_cta_ok,
    _landing_headline_ok,
    _normalize_blueprint_output,
    _precompute_pmm_analysis,
    _strip_landing_preamble,
    _TRAILING_CONJ,
    _validate_blueprint_output,
    _WEAK_ALT_TOKENS,
)
from agents.writing.linkedin import (  # noqa: F401
    LinkedInWriterMixin,
)
from agents.writing.ux import (  # noqa: F401
    UXWriterMixin,
    _clean_ux_context,
    _CTA_INTERNAL_BANNED,
    _normalize_ux_output,
    _UX_BANNED,
    _ux_cta_ok,
    _UX_DOMAIN_DRIFT,
    _ux_domain_drift_cleanup,
    _UX_HEADERS,
    _UX_PLACEHOLDER_SUBSTRINGS,
    _UX_PRODUCT_BANNED,
    _UX_PRODUCT_CONCRETE_ACTIONS,
    _UX_PRODUCT_OPERATOR_TERMS,
    _UX_PRODUCT_SCENARIO_TAGS,
    _validate_ux_output,
)
from agents.writing.launch_pack import (  # noqa: F401
    LaunchPackWriterMixin,
)
from agents.writing.positioning import (  # noqa: F401
    PositioningWriterMixin,
    score_positioning,
    _normalize_positioning_output,
    _POSITIONING_BANNED,
    _POSITIONING_HEADERS,
    _positioning_sections_distinct,
    _validate_positioning_output,
)
from agents.writing.grounding import (  # noqa: F401
    GroundingAgent,
)


@dataclass
class WritingAgent(
    LandingWriterMixin,
    LinkedInWriterMixin,
    UXWriterMixin,
    LaunchPackWriterMixin,
    PositioningWriterMixin,
):
    name: str = "WritingAgent"
    # Preloaded positioning decisions from product_profile.json (the Messaging Brain).
    # When set, extract_positioning_decisions() uses these directly instead of calling the LLM.
    brain_decisions: Optional[dict] = None
    # Strategy layers — set by main.py / API before calling generators.
    # When set, generators use these for deeper product-grounded output.
    positioning: Optional[object] = None   # PositioningContext
    narrative: Optional[object] = None     # NarrativeContext


# Agents that used to live in this file. Re-exported for backward compatibility.
from agents.critic_agent import CriticAgent  # noqa: E402,F401
from agents.fact_guard_agent import FactGuardAgent  # noqa: E402,F401
from agents.strategist_agent import StrategistAgent  # noqa: E402,F401
