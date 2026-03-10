"""Generation context builder: merges brain, brief, and user overrides into a single generation input.

Merge priority (highest wins):
  1. User overrides (latest prompt edits from API or CLI)
  2. Messaging Brain (product_profile.json decisions)
  3. Brief (brief.json baseline)

COHERENCE RULE: If brain and brief clearly refer to different products,
brief-only fields (tone, cta, examples, context) are SUPPRESSED to prevent
hybrid outputs. The brain is treated as the canonical source of truth.

This module also provides readiness assessment for different output modes.
"""

from __future__ import annotations

import hashlib
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
    # Set to True if brain and brief were detected as referring to different products
    cross_product_detected: bool = False
    # Human-readable explanation of what was suppressed/repaired
    coherence_notes: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Coherence detection
# ---------------------------------------------------------------------------

def _product_fingerprint(product: str, audience: str, problem: str) -> str:
    """Short hash of normalized core identity fields."""
    raw = f"{(product or '').strip().lower()}|{(audience or '').strip().lower()}|{(problem or '').strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _words(s: str) -> set[str]:
    """Lowercase word set, stripped of punctuation."""
    return set(w.strip(".,;:!?\"'()") for w in (s or "").lower().split() if len(w.strip(".,;:!?\"'()")) > 2)


def _products_refer_to_same_thing(
    brain_product: str, brain_audience: str, brain_problem: str,
    brief_product: str, brief_audience: str, brief_pain: str,
) -> bool:
    """Return True if brain and brief plausibly describe the same product.

    Uses product name overlap as primary signal, audience/problem as secondary.
    Designed to catch obvious mismatches (gaushala vs AI UX operator) while
    allowing minor wording differences in the same product.
    """
    bp = (brain_product or "").strip().lower()
    fp = (brief_product or "").strip().lower()

    # If either is empty, can't compare — assume coherent (first-run case)
    if not bp or not fp:
        return True

    # Exact match or containment
    if bp == fp or bp in fp or fp in bp:
        return True

    # Significant word overlap in product names
    bp_words = _words(brain_product)
    fp_words = _words(brief_product)
    if bp_words and fp_words:
        overlap = len(bp_words & fp_words) / min(len(bp_words), len(fp_words))
        if overlap >= 0.4:
            return True

    # Cross-check: do audience or problem fields share significant vocabulary?
    ba_words = _words(brain_audience)
    fa_words = _words(brief_audience)
    bpain_words = _words(brain_problem)
    fpain_words = _words(brief_pain)

    aud_overlap = len(ba_words & fa_words) / max(min(len(ba_words), len(fa_words)), 1)
    pain_overlap = len(bpain_words & fpain_words) / max(min(len(bpain_words), len(fpain_words)), 1)

    # If both audience AND pain have zero overlap, these are clearly different products
    if aud_overlap < 0.2 and pain_overlap < 0.2:
        return False

    # Ambiguous — give benefit of the doubt
    return True


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

    COHERENCE RULE: If brain and brief refer to different products, brief-only
    fields (tone, cta, examples, context) are suppressed to prevent hybrid output.

    Args:
        brief: ClientBrief instance (or None)
        profile: ProductProfile instance (or None)
        overrides: dict of field-level overrides from user (prompt edits, API payload)
    """
    overrides = overrides or {}
    decisions = {}
    sources: dict[str, str] = {}
    coherence_notes: list[str] = []
    cross_product = False

    # Start with brain decisions if available
    if profile and getattr(profile, "decisions", None):
        decisions = dict(profile.decisions)

    # Apply decision-level overrides
    for key in ("icp", "primary_problem", "current_alternative", "desired_outcome",
                "category_frame", "differentiation", "anti_positioning"):
        if overrides.get(key):
            decisions[key] = overrides[key]

    # --- Coherence check: do brain and brief refer to the same product? ---
    if profile and brief:
        brain_product = clean_phrase(getattr(profile, "product", "") or "") or ""
        brain_audience = (decisions.get("icp") or getattr(profile, "audience", "") or "")
        brain_problem = (decisions.get("primary_problem") or getattr(profile, "problem", "") or "")
        brief_product = getattr(brief, "product", "") or ""
        brief_audience = getattr(brief, "audience", "") or ""
        brief_pain = getattr(brief, "pain", "") or ""

        if not _products_refer_to_same_thing(
            brain_product, brain_audience, brain_problem,
            brief_product, brief_audience, brief_pain,
        ):
            cross_product = True
            coherence_notes.append(
                f"CROSS-PRODUCT DETECTED: brain='{brain_product}' vs brief='{brief_product}'. "
                f"Brief-only fields (tone, cta, examples, context) suppressed. Brain is canonical."
            )

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

    def _pick_brief_only(field_name: str, override_key: str, brief_val: str) -> str:
        """Pick from overrides > brief, but suppress brief if cross-product."""
        ov = (overrides.get(override_key) or "").strip()
        if ov:
            sources[field_name] = "override"
            return ov
        if cross_product:
            # Brief value belongs to a different product — suppress it
            sources[field_name] = "suppressed (cross-product)"
            return ""
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

    # Tone: override > brain.tone > brief.tone (brief suppressed if cross-product)
    tone_brain = getattr(p, "tone", "") if p else ""
    tone_brief = getattr(b, "tone", "") if b else ""
    if cross_product and not tone_brain and not (overrides.get("tone") or "").strip():
        # Suppress stale brief tone
        tone = ""
        sources["tone"] = "suppressed (cross-product)"
    else:
        tone = _pick("tone", "tone", tone_brain, tone_brief)

    # CTA, examples, context: use _pick_brief_only (suppressed if cross-product)
    cta = _pick_brief_only("cta", "cta", getattr(b, "cta", "") if b else "")
    examples = _pick_brief_only("examples", "examples", getattr(b, "examples", "") if b else "")
    context_brain = getattr(p, "context", "") if p else ""
    context_brief = getattr(b, "context", "") if b else ""
    if cross_product:
        # Suppress brief context — it describes a different product
        context = _pick("context", "context", context_brain, "")
        if not context:
            sources["context"] = "suppressed (cross-product)"
    else:
        context = _pick("context", "context", context_brain, context_brief)

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
        cross_product_detected=cross_product,
        coherence_notes=coherence_notes,
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
