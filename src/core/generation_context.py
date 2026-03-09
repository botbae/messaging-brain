"""Generation context builder: merges brain, brief, and user overrides into a single generation input.

Merge priority (highest wins):
  1. User overrides (latest prompt edits from API or CLI)
  2. Messaging Brain (product_profile.json decisions)
  3. Brief (brief.json baseline)

This module also provides readiness assessment for different output modes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.utils import clean_phrase, clean_sentence


@dataclass
class GenerationContext:
    """Unified input for all generators. Carries merged brief fields + decisions + metadata."""

    product: str = ""
    audience: str = ""
    pain: str = ""
    offer: str = ""
    tone: str = ""
    cta: str = ""
    examples: str = ""
    context: str = ""
    decisions: dict = field(default_factory=dict)
    # Tracks where each field came from for transparency / debugging
    sources: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Readiness assessment
# ---------------------------------------------------------------------------

# Fields required per mode to produce meaningful output
_MODE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "landing": ("product", "audience", "pain"),
    "positioning": ("product", "audience", "pain"),
    "linkedin": ("product", "audience", "pain"),
    "ux": ("product", "audience", "pain", "offer"),
    "ux_product": ("product", "audience", "pain", "offer"),
    "ux_operator": (),  # operator UX is app-specific, no brief needed
    "ux_microcopy": ("product",),
    "launch_pack": ("product", "audience"),
    "audit": ("product",),
    "brain": ("product",),
    "idea": (),
}

# Decision fields that strengthen output quality per mode
_MODE_DECISION_WANTS: dict[str, tuple[str, ...]] = {
    "landing": ("icp", "primary_problem", "current_alternative", "desired_outcome", "differentiation"),
    "positioning": ("icp", "primary_problem", "current_alternative", "desired_outcome", "category_frame", "differentiation", "anti_positioning"),
    "ux": ("icp", "primary_problem", "desired_outcome", "category_frame"),
    "ux_product": ("icp", "primary_problem", "desired_outcome", "category_frame"),
    "linkedin": ("icp", "primary_problem", "differentiation"),
}


@dataclass
class ReadinessResult:
    ready: bool
    missing_required: list[str] = field(default_factory=list)
    missing_recommended: list[str] = field(default_factory=list)
    message: str = ""


def assess_readiness(ctx: GenerationContext, mode: str) -> ReadinessResult:
    """Check whether the generation context has enough data for the requested mode."""
    required = _MODE_REQUIREMENTS.get(mode, ())
    field_map = {
        "product": ctx.product,
        "audience": ctx.audience,
        "pain": ctx.pain,
        "offer": ctx.offer,
    }
    missing_req = [f for f in required if not (field_map.get(f) or "").strip()]

    wanted = _MODE_DECISION_WANTS.get(mode, ())
    missing_rec = [f for f in wanted if not (ctx.decisions.get(f) or "").strip()]

    if missing_req:
        msg = (
            f"Not ready for {mode}. Missing required fields: {', '.join(missing_req)}. "
            "Run --mode brain or provide a more complete brief first."
        )
        return ReadinessResult(ready=False, missing_required=missing_req, missing_recommended=missing_rec, message=msg)

    msg = ""
    if missing_rec:
        msg = (
            f"Ready for {mode}, but output quality would improve with: {', '.join(missing_rec)}. "
            "Consider running --mode brain with a fuller brief."
        )
    return ReadinessResult(ready=True, missing_required=[], missing_recommended=missing_rec, message=msg)


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def build_generation_context(
    brief: Optional[object] = None,
    profile: Optional[object] = None,
    overrides: Optional[dict] = None,
) -> GenerationContext:
    """Build a merged GenerationContext from brief, brain profile, and user overrides.

    Merge order per field (first non-empty wins):
      1. overrides[field]  — latest user edits
      2. profile / profile.decisions  — saved Messaging Brain
      3. brief.field  — baseline brief

    Args:
        brief: ClientBrief instance (or None)
        profile: ProductProfile instance (or None)
        overrides: dict of field-level overrides from user (prompt edits, API payload)
    """
    overrides = overrides or {}
    decisions = {}
    sources: dict[str, str] = {}

    # Start with brain decisions if available
    if profile and getattr(profile, "decisions", None):
        decisions = dict(profile.decisions)

    # Apply decision-level overrides
    for key in ("icp", "primary_problem", "current_alternative", "desired_outcome",
                "category_frame", "differentiation", "anti_positioning"):
        if overrides.get(key):
            decisions[key] = overrides[key]

    def _pick(field_name: str, override_key: str, brain_val: str, brief_val: str) -> str:
        """Pick first non-empty value from overrides > brain > brief."""
        ov = (overrides.get(override_key) or "").strip()
        if ov:
            sources[field_name] = "override"
            return ov
        bv = (brain_val or "").strip()
        if bv:
            sources[field_name] = "brain"
            return bv
        fv = (brief_val or "").strip()
        if fv:
            sources[field_name] = "brief"
            return fv
        sources[field_name] = "empty"
        return ""

    d = decisions
    p = profile
    b = brief

    # Product: override > brain.product > brief.product
    product_brain = clean_phrase(getattr(p, "product", "") or "") if p else ""
    product_brief = getattr(b, "product", "") if b else ""
    product = _pick("product", "product", product_brain, product_brief)

    # Audience: override > decisions.icp > brain.audience > brief.audience
    aud_brain = d.get("icp") or (getattr(p, "audience", "") if p else "")
    aud_brief = getattr(b, "audience", "") if b else ""
    audience = _pick("audience", "audience", aud_brain, aud_brief)

    # Pain: override > decisions.primary_problem > brain.problem > brief.pain
    pain_brain = d.get("primary_problem") or (getattr(p, "problem", "") if p else "")
    pain_brief = getattr(b, "pain", "") if b else ""
    pain = _pick("pain", "pain", pain_brain, pain_brief)

    # Offer: override > decisions.desired_outcome > decisions.differentiation > brain.advantage > brief.offer
    offer_brain = (
        d.get("desired_outcome")
        or d.get("differentiation")
        or (getattr(p, "advantage", "") if p else "")
    )
    offer_brief = getattr(b, "offer", "") if b else ""
    offer = _pick("offer", "offer", offer_brain, offer_brief)

    # Tone: override > brain.tone > brief.tone
    tone_brain = getattr(p, "tone", "") if p else ""
    tone_brief = getattr(b, "tone", "") if b else ""
    tone = _pick("tone", "tone", tone_brain, tone_brief)

    # CTA, examples, context: override > brief (brain doesn't store these)
    cta = _pick("cta", "cta", "", getattr(b, "cta", "") if b else "")
    examples = _pick("examples", "examples", "", getattr(b, "examples", "") if b else "")
    context = _pick("context", "context",
                    getattr(p, "context", "") if p else "",
                    getattr(b, "context", "") if b else "")

    return GenerationContext(
        product=product,
        audience=audience,
        pain=pain,
        offer=offer,
        tone=tone,
        cta=cta,
        examples=examples,
        context=context,
        decisions=decisions,
        sources=sources,
    )


def context_to_brief(ctx: GenerationContext):
    """Convert a GenerationContext back to a ClientBrief for backward compatibility."""
    from agents.writing_agent import ClientBrief
    return ClientBrief(
        product=ctx.product,
        audience=ctx.audience,
        pain=ctx.pain,
        offer=ctx.offer,
        tone=ctx.tone,
        cta=ctx.cta,
        examples=ctx.examples,
        context=ctx.context,
    )
