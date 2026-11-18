"""Confidence engine — scores a ProductProfile and produces a ConfidenceReport.

Entirely rule-based: no LLM calls.

Reads per-entry LLM confidence from DecisionDict._meta when available (set
during idea extraction or brain mode) and applies heuristic scoring on top.

Usage:
    from core.confidence_engine import score_decision_state, save_confidence_report, load_confidence_report
    report = score_decision_state(profile, client_name="my-client")
    save_confidence_report(report, "my-client")
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from product_profile import (
    ProductProfile,
    _contextual_suggestion,
    _is_generic,
    _word_count,
    _PAIN_WORDS,
    _FEATURE_WORDS,
    _ROLE_NOUNS,
)
from schemas.confidence_report import ConfidenceReport, FieldScore
from core.paths import client_dir as safe_client_dir


# ---------------------------------------------------------------------------
# Field configuration
# ---------------------------------------------------------------------------

# Maps public field names to DecisionDict keys so we can read LLM confidence.
_FIELD_TO_DECISION_KEY: dict[str, str] = {
    "audience":      "icp",
    "problem":       "primary_problem",
    "advantage":     "differentiation",
    "alternatives":  "current_alternative",
    "goal":          "desired_outcome",
    "category_frame": "category_frame",
    "anti_positioning": "anti_positioning",
}

# Weight multiplier used in overall score calculation.
# Critical fields are worth 2× to better reflect their blocking impact.
_FIELD_WEIGHTS: dict[str, float] = {
    "product":       2.0,
    "audience":      2.0,
    "problem":       2.0,
    "advantage":     2.0,
    "alternatives":  1.0,
    "goal":          1.0,
    "tone":          0.5,
    "category_frame": 0.5,
}

_CRITICAL_FIELDS: frozenset[str] = frozenset({"product", "audience", "problem", "advantage"})

# Recommendations shown when a field is missing.
_MISSING_RECS: dict[str, str] = {
    "product":       "Add a product name and a one-line descriptor of what it does.",
    "audience":      "Describe who this is built for — name the role, stage, or company type.",
    "problem":       "Describe the core pain your product solves — name what breaks or costs when this isn't fixed.",
    "advantage":     "Describe what makes this product structurally different from the alternatives.",
    "alternatives":  "List the specific tools or manual behaviors users currently rely on instead.",
    "goal":          "Describe the specific outcome the user achieves after using the product.",
    "tone":          "Add a tone descriptor (e.g. 'direct and strategic', 'warm and practical').",
    "category_frame": "Add a short category label (e.g. 'positioning engine for founders').",
}


# ---------------------------------------------------------------------------
# Per-field scoring
# ---------------------------------------------------------------------------

def _score_field(
    field_name: str,
    value: str,
    profile: ProductProfile,
    llm_confidence: Optional[float] = None,
) -> tuple[float, str, Optional[str], Optional[str]]:
    """Score one field. Returns (score, status, recommendation, example)."""
    v = (value or "").strip()

    # --- MISSING ---
    if not v:
        rec = _MISSING_RECS.get(field_name, f"Add a value for '{field_name}'.")
        example = _contextual_suggestion(field_name, profile) or None
        return 0.0, "missing", rec, example

    v_lower = v.lower()
    wc = _word_count(v)

    # --- GENERIC PLACEHOLDER ---
    if _is_generic(v):
        rec = _MISSING_RECS.get(field_name, f"'{field_name}' is too generic — be more specific.")
        example = _contextual_suggestion(field_name, profile) or None
        return 0.25, "weak", rec, example

    # --- FIELD-SPECIFIC HEURISTICS ---
    score: float
    status: str
    rec: Optional[str] = None
    example: Optional[str] = None

    if field_name == "product":
        if wc == 0:
            # Should already be caught by the blank check above, but be safe
            score, status = 0.0, "missing"
            rec = _MISSING_RECS["product"]
        elif wc == 1 and v[0].isupper():
            # A single proper-noun name (e.g. "Unimind", "Slack") — real but needs a descriptor
            score, status = 0.6, "draft"
            rec = "Add a one-line descriptor to the product name (e.g. 'Unimind: positioning engine for founders')."
        elif wc < 2:
            # Single lowercase word — likely a placeholder
            score, status = 0.4, "weak"
            rec = "Product name is too short — add a one-line descriptor (e.g. 'Unimind: positioning engine for founders')."
        else:
            score, status = 0.9, "strong"

    elif field_name == "audience":
        has_role = any(rn in v_lower.split() for rn in _ROLE_NOUNS)
        if wc <= 2 and not has_role:
            score, status = 0.25, "weak"
            rec = "Audience is too broad — name a specific role (e.g. 'early-stage B2B founders')."
            example = _contextual_suggestion("audience", profile) or None
        elif wc <= 4 and not has_role:
            score, status = 0.5, "draft"
            rec = "Audience could be more specific — add a qualifier (stage, company size, or vertical)."
            example = _contextual_suggestion("audience", profile) or None
        else:
            score, status = 0.85, "strong"

    elif field_name == "problem":
        hit_feature = next((fw for fw in _FEATURE_WORDS if fw in v_lower), None)
        if hit_feature:
            score, status = 0.35, "weak"
            rec = (
                f"Problem mentions '{hit_feature}' — that describes a feature, not a pain. "
                "Describe the consequence the user experiences instead."
            )
            example = _contextual_suggestion("problem", profile) or None
        elif wc <= 4 and not any(pw in v_lower for pw in _PAIN_WORDS):
            score, status = 0.4, "draft"
            rec = "Problem is short and doesn't name a consequence — add what breaks, slows down, or costs money."
            example = _contextual_suggestion("problem", profile) or None
        elif wc <= 7:
            score, status = 0.65, "draft"
        else:
            score, status = 0.9, "strong"

    elif field_name == "advantage":
        if wc <= 3:
            score, status = 0.35, "weak"
            rec = "Advantage is too short — describe the structural reason this product wins over alternatives."
            example = _contextual_suggestion("advantage", profile) or None
        elif wc <= 6:
            score, status = 0.6, "draft"
            rec = "Advantage could be sharper — name what makes this structurally different, not just better."
            example = _contextual_suggestion("advantage", profile) or None
        else:
            score, status = 0.87, "strong"

    elif field_name == "alternatives":
        if wc <= 2:
            score, status = 0.3, "weak"
            rec = "Alternatives is too vague — name the specific tools or workflows users rely on instead."
            example = _contextual_suggestion("alternatives", profile) or None
        elif wc <= 4:
            score, status = 0.6, "draft"
        else:
            score, status = 0.82, "strong"

    elif field_name == "goal":
        if wc <= 3:
            score, status = 0.4, "draft"
            rec = "Goal is too short — describe the specific outcome: what changes for the user after using this product?"
            example = _contextual_suggestion("goal", profile) or None
        else:
            score, status = 0.8, "strong"

    elif field_name == "tone":
        if wc < 2:
            score, status = 0.5, "draft"
            rec = "Tone could be richer — add a second descriptor (e.g. 'direct and strategic')."
        else:
            score, status = 0.85, "strong"

    else:
        # Generic fallback for unmapped fields
        if wc <= 2:
            score, status = 0.4, "draft"
        elif wc <= 5:
            score, status = 0.65, "draft"
        else:
            score, status = 0.8, "strong"

    # LLM confidence downward cap: if the extractor was uncertain, don't claim "strong"
    if llm_confidence is not None and llm_confidence < 0.65:
        score = min(score, llm_confidence)
        if status == "strong":
            status = "draft"

    return score, status, rec, example


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_decision_state(
    profile: ProductProfile,
    client_name: str = "",
) -> ConfidenceReport:
    """Score each field in a ProductProfile and return a ConfidenceReport.

    Entirely rule-based — no LLM calls.
    Incorporates per-entry LLM confidence from DecisionDict._meta when available.
    """
    decisions = profile.decisions or {}
    now = datetime.now(timezone.utc).isoformat()

    # (field_name, resolved_value, is_critical)
    field_defs: list[tuple[str, str, bool]] = [
        ("product",       profile.product or "",                                              True),
        ("audience",      decisions.get("icp") or profile.audience or "",                    True),
        ("problem",       decisions.get("primary_problem") or profile.problem or "",          True),
        ("advantage",     decisions.get("differentiation") or profile.advantage or "",        True),
        ("alternatives",  decisions.get("current_alternative") or profile.alternatives or "", False),
        ("goal",          decisions.get("desired_outcome") or profile.goal or "",             False),
        ("tone",          decisions.get("tone") or profile.tone or "",                        False),
        ("category_frame", decisions.get("category_frame") or "",                            False),
    ]

    scored: list[FieldScore] = []
    critical_total = 0.0
    critical_weight = 0.0

    for field_name, value, is_critical in field_defs:
        # Pull LLM-assigned confidence from DecisionDict metadata when available.
        # Only act on it when the LLM signalled low certainty (< 0.85).
        dec_key = _FIELD_TO_DECISION_KEY.get(field_name)
        llm_conf: Optional[float] = None
        if dec_key and hasattr(decisions, "get_entry"):
            entry = decisions.get_entry(dec_key)
            if entry:
                raw_conf = entry.get("confidence")
                if raw_conf is not None and float(raw_conf) < 0.85:
                    llm_conf = float(raw_conf)

        score, status, rec, example = _score_field(field_name, value, profile, llm_conf)
        weight = _FIELD_WEIGHTS.get(field_name, 1.0)

        if is_critical:
            critical_total += score * weight
            critical_weight += weight

        scored.append(FieldScore(
            field_name=field_name,
            score=round(score, 2),
            status=status,
            is_critical=is_critical,
            value_preview=value[:120] if value else None,
            recommendation=rec,
            example=example,
        ))

    # Sort: critical blockers first (missing/weak), then ascending by score
    scored.sort(
        key=lambda x: (
            0 if (x.is_critical and x.status in ("missing", "weak")) else 1,
            x.score,
        )
    )

    overall = round(critical_total / critical_weight, 2) if critical_weight > 0 else 0.0
    blocker_count = sum(
        1 for fs in scored if fs.is_critical and fs.status in ("missing", "weak")
    )
    generation_safe = overall >= 0.65 and blocker_count == 0

    # Human-readable summary
    if generation_safe:
        summary = f"Brain is ready for generation. Critical field confidence: {overall:.0%}."
    elif blocker_count > 0:
        blockers = [fs.field_name for fs in scored if fs.is_critical and fs.status in ("missing", "weak")]
        summary = (
            f"Brain needs improvement before safe generation. "
            f"{len(blockers)} critical field(s) need attention: {', '.join(blockers)}."
        )
    else:
        # Overall below threshold but no hard blockers — critical fields are present but shallow
        summary = (
            f"Brain needs improvement before safe generation. "
            f"Critical confidence is {overall:.0%} — sharpen the core fields to reach 65%."
        )

    # Best next action: critical blockers first; if none, lowest-scoring critical field;
    # then non-critical missing/weak fields as a last resort.
    worst = (
        next((fs for fs in scored if fs.status == "missing" and fs.is_critical), None)
        or next((fs for fs in scored if fs.status == "weak" and fs.is_critical), None)
        or min(
            (fs for fs in scored if fs.is_critical),
            key=lambda x: x.score,
            default=None,
        )
        or next((fs for fs in scored if fs.status in ("missing", "weak")), None)
    )
    next_action = worst.recommendation if worst and worst.recommendation else None

    return ConfidenceReport(
        client_name=client_name or profile.client_name or "",
        generated_at=now,
        brain_version=profile.brain_version,
        overall_score=overall,
        generation_safe=generation_safe,
        blocker_count=blocker_count,
        field_scores=scored,
        summary=summary,
        next_action=next_action,
    )


def save_confidence_report(report: ConfidenceReport, client_slug: str) -> Path:
    """Persist confidence report to clients/<client>/confidence_report.json."""
    path = safe_client_dir(client_slug) / "confidence_report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(), f, indent=2)
    return path


def load_confidence_report(client_slug: str) -> Optional[ConfidenceReport]:
    """Load saved confidence report from clients/<client>/confidence_report.json."""
    path = safe_client_dir(client_slug) / "confidence_report.json"
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return ConfidenceReport(**data)
    except Exception:
        return None
