"""Thin FastAPI wrapper for the Unimind backend.

Local prototyping only — no auth, no database, no production infra.

Run from the repo root:
    PYTHONPATH=src uvicorn src.api.app:app --reload --port 8001

Interactive docs: http://localhost:8001/docs
"""

import logging
import sys
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Ensure src/ is on the path when uvicorn loads this module from repo root.
_src = Path(__file__).parent.parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agents.writing_agent import ClientBrief
from core.brief import brief_from_file
from core.generation_context import (
    assess_readiness,
    build_generation_context,
    context_to_brief,
)
from core.strategy_context import (
    assess_narrative_readiness,
    build_strategy_layers,
)
from core.client_state import init_client_state
from core.utils import clean_phrase
from main import (
    _load_profile_if_exists,
    _run_brain_mode,
    _run_generate,
    _run_idea_mode,
)
from product_profile import ProductProfile, score_brain_strength, suggest_brain_improvements

app = FastAPI(
    title="Unimind API",
    description="Local prototyping API — not for production use.",
    version="0.1.0",
)

# Local frontend prototyping — allow Next.js dev server to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["Content-Type"],
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class IdeaRequest(BaseModel):
    idea: str
    client: Optional[str] = None


class BriefData(BaseModel):
    product: str = ""
    audience: str = ""
    pain: str = ""
    offer: str = ""
    tone: str = ""
    cta: str = ""
    context: str = ""
    examples: str = ""


class BrainRequest(BaseModel):
    client: str
    brief: BriefData


class GenerateRequest(BaseModel):
    client: str
    # Optional overrides — latest user edits that should take priority over saved brain/brief
    product: Optional[str] = None
    audience: Optional[str] = None
    pain: Optional[str] = None
    offer: Optional[str] = None
    tone: Optional[str] = None
    cta: Optional[str] = None
    context: Optional[str] = None
    # Decision-level overrides
    icp: Optional[str] = None
    primary_problem: Optional[str] = None
    current_alternative: Optional[str] = None
    desired_outcome: Optional[str] = None
    category_frame: Optional[str] = None
    differentiation: Optional[str] = None
    anti_positioning: Optional[str] = None


class IdeaExtractData(BaseModel):
    product: str = ""
    icp: str = ""
    problem: str = ""
    category: str = ""
    differentiation: str = ""


class BrainSaveRequest(BaseModel):
    client: str
    idea_extract: IdeaExtractData


class ClientInitRequest(BaseModel):
    client: str
    reset_brief: bool = False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_profile(profile: ProductProfile) -> dict:
    """Return only user-facing profile fields.

    Strips internal metadata (confidence, source_notes, fingerprint,
    timestamps, version counter) that the frontend should never see.
    """
    safe_decisions: dict = {}
    if profile.decisions:
        # DecisionDict stores plain strings as values — iterate to get them
        for k, v in profile.decisions.items():
            safe_decisions[k] = v
    return {
        "product": profile.product,
        "audience": profile.audience,
        "problem": profile.problem,
        "alternatives": profile.alternatives,
        "advantage": profile.advantage,
        "tone": profile.tone,
        "goal": profile.goal,
        "context": profile.context,
        "decisions": safe_decisions,
    }


def _normalize_brain_strength(raw) -> str | None:
    """Normalize brain_strength to a simple lowercase label for the frontend.

    Accepts the dict returned by score_brain_strength(), a raw string, or None.
    Always returns one of "weak", "moderate", "strong", or None.
    """
    if raw is None:
        return None
    # score_brain_strength returns {"score": float, "label": str, "field_scores": ...}
    if isinstance(raw, dict):
        raw = raw.get("label", "")
    label = str(raw).strip().lower()
    _MAP = {
        "strong": "strong", "high": "strong", "good": "strong",
        "moderate": "moderate", "medium": "moderate", "decent": "moderate", "ok": "moderate",
        "weak": "weak", "low": "weak", "incomplete": "weak", "poor": "weak",
    }
    return _MAP.get(label)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/idea")
def idea(req: IdeaRequest):
    """Extract ICP, problem, category, and differentiation from a product idea string."""
    client_slug = clean_phrase(req.client) if req.client else None
    logger.info("POST /idea client=%s", client_slug or "(anonymous)")
    result, profile_path = _run_idea_mode(req.idea, client_slug=client_slug)
    if result is None:
        raise HTTPException(status_code=500, detail="Idea extraction failed. Check that Ollama is running.")

    brain_suggestions = None
    brain_strength = None
    if profile_path and Path(profile_path).exists():
        _profile = ProductProfile.load(profile_path)
        _suggestions = suggest_brain_improvements(_profile)
        if _suggestions:
            brain_suggestions = _suggestions
        brain_strength = _normalize_brain_strength(score_brain_strength(_profile))

    return {
        "client": client_slug or "",
        "suggested_slug": result.get("suggested_slug", ""),
        "idea_extract": result,
        "brain_suggestions": brain_suggestions,
        "brain_strength": brain_strength,
    }


@app.post("/brain")
def brain(req: BrainRequest):
    """Run full positioning LLM pass and save product_profile.json for the client."""
    client_slug = clean_phrase(req.client)
    logger.info("POST /brain client=%s", client_slug)
    brief = ClientBrief(
        product=req.brief.product,
        audience=req.brief.audience,
        pain=req.brief.pain,
        offer=req.brief.offer,
        tone=req.brief.tone,
        cta=req.brief.cta,
        examples=req.brief.examples,
        context=req.brief.context,
    )
    profile, _ = _run_brain_mode(brief, client_slug)
    _brain_suggestions = suggest_brain_improvements(profile)
    _brain_strength = _normalize_brain_strength(score_brain_strength(profile))
    return {
        "client": client_slug,
        "product_profile": _safe_profile(profile),
        "brain_suggestions": _brain_suggestions if _brain_suggestions else None,
        "brain_strength": _brain_strength,
    }


@app.post("/client/init")
def client_init(req: ClientInitRequest):
    """Initialize or reset a client directory.

    Removes brain, idea extract, and output files for a fresh start.
    Optionally invalidates an existing brief (reset_brief=true).
    """
    client_slug = clean_phrase(req.client)
    if not client_slug:
        raise HTTPException(status_code=400, detail="client is required")
    logger.info("POST /client/init client=%s reset_brief=%s", client_slug, req.reset_brief)
    result = init_client_state(client_slug, reset_brief=req.reset_brief)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return {"client": client_slug, **{k: v for k, v in result.items() if k != "error"}}


@app.post("/generate/landing")
def generate_landing(req: GenerateRequest):
    """Generate a landing page for the client using their stored brain."""
    return _run_generate_endpoint(req, "landing")


@app.post("/generate/ux")
def generate_ux(req: GenerateRequest):
    """Generate a UX pack for the client using their stored brain.

    Note: UX copy generation is de-scoped from the V1 main flow.
    The primary artifact is now the Landing Page Blueprint (POST /generate/landing).
    This endpoint remains available for direct use but is not featured in the UI.
    """
    return _run_generate_endpoint(req, "ux")


@app.post("/generate/positioning")
def generate_positioning(req: GenerateRequest):
    """Generate a positioning document for the client using their stored brain."""
    return _run_generate_endpoint(req, "positioning")


@app.post("/generate/linkedin")
def generate_linkedin(req: GenerateRequest):
    """Generate a LinkedIn post for the client using their stored brain."""
    return _run_generate_endpoint(req, "linkedin")


@app.post("/generate/launch_pack")
def generate_launch_pack(req: GenerateRequest):
    """Generate a launch pack for the client using their stored brain."""
    return _run_generate_endpoint(req, "launch_pack")


@app.post("/generate/{mode}")
def generate_any(mode: str, req: GenerateRequest):
    """Generic generation endpoint for any supported mode."""
    valid_modes = {"landing", "linkedin", "ux", "ux_product", "ux_operator", "ux_microcopy",
                   "launch_pack", "audit", "positioning"}
    if mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Unknown mode '{mode}'. Valid: {sorted(valid_modes)}")
    return _run_generate_endpoint(req, mode)


@app.get("/readiness/{client}/{mode}")
def check_readiness(client: str, mode: str):
    """Check whether a client has enough data for a given output mode."""
    client_slug = clean_phrase(client)
    profile = _load_profile_if_exists(client_slug)
    brief_path = Path("clients") / client_slug / "brief.json"
    brief = brief_from_file(str(brief_path)) if brief_path.exists() else None

    if not profile and not brief:
        raise HTTPException(status_code=404, detail=f"No data for client '{client_slug}'.")

    gen_ctx = build_generation_context(brief=brief, profile=profile)
    readiness = assess_readiness(gen_ctx, mode)
    return {
        "client": client_slug,
        "mode": mode,
        "ready": readiness.ready,
        "missing_required": readiness.missing_required,
        "missing_recommended": readiness.missing_recommended,
        "message": readiness.message,
    }


@app.post("/brain/save")
def brain_save(req: BrainSaveRequest):
    """Persist edited Messaging Brain fields back to the client's product_profile.json.

    Field mapping (idea_extract → stored decisions):
      icp            → decisions.icp
      problem        → decisions.primary_problem  + top-level profile.problem
      category       → decisions.category_frame
      differentiation→ decisions.differentiation  + top-level profile.advantage
    All other existing fields are preserved unchanged.
    """
    client_slug = clean_phrase(req.client)
    profile_path = Path("clients") / client_slug / "product_profile.json"

    if not profile_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No product_profile.json found at {profile_path}. Run POST /brain first.",
        )

    profile = ProductProfile.load(profile_path)

    # Apply edits — only overwrite non-empty values so a partial save doesn't blank fields.
    edits = req.idea_extract
    if edits.product:
        profile.product = edits.product.strip()
    if edits.icp:
        profile.decisions["icp"] = edits.icp
    if edits.problem:
        profile.decisions["primary_problem"] = edits.problem
        profile.problem = edits.problem
    if edits.category:
        profile.decisions["category_frame"] = edits.category
    if edits.differentiation:
        profile.decisions["differentiation"] = edits.differentiation
        profile.advantage = edits.differentiation

    profile.save(profile_path)
    logger.info("POST /brain/save client=%s — profile updated", client_slug)
    return {"client": client_slug, "product_profile": _safe_profile(profile)}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_slots_from_blueprint(text: str) -> dict:
    """Extract landing page slots from a blueprint document.

    Maps blueprint sections to the slot schema:
      headline, subhead, problem, why_current_options_fail, what_this_is, primary_cta
    """
    import re

    def _field(label: str) -> str:
        """Extract a labeled field value like 'Headline: ...' from the text."""
        pattern = rf'{re.escape(label)}\s*:\s*(.+)'
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(1).strip().strip('"\'') if m else ""

    def _section_body(header: str, next_headers: tuple) -> str:
        """Extract body text between a section header and the next header."""
        idx = text.find(header)
        if idx < 0:
            return ""
        start = idx + len(header)
        end = len(text)
        for nh in next_headers:
            ni = text.find(nh, start)
            if 0 < ni < end:
                end = ni
        body = text[start:end].strip()
        # Remove labeled sub-fields, keep just the prose
        lines = [l.strip() for l in body.splitlines() if l.strip() and not re.match(r'^(Purpose|Headline|Subhead|Primary CTA|Proof line)\s*:', l)]
        return " ".join(lines[:3])

    _NEXT = ("POSITIONING SUMMARY", "HERO", "PROBLEM SECTION", "WHY CURRENT OPTIONS FAIL",
             "PRODUCT EXPLANATION", "HOW IT WORKS", "PROOF / CREDIBILITY",
             "FINAL CTA SECTION", "UX / CONTENT NOTES", "OPTIONAL FUTURE SECTIONS")

    return {
        "headline": _field("Headline"),
        "subhead": _field("Subhead"),
        "problem": _section_body("PROBLEM SECTION", _NEXT),
        "why_current_options_fail": _section_body("WHY CURRENT OPTIONS FAIL", _NEXT),
        "what_this_is": _section_body("PRODUCT EXPLANATION", _NEXT),
        "primary_cta": _field("Primary CTA"),
    }


def _run_generate_endpoint(req: GenerateRequest, mode: str) -> dict:
    client_slug = clean_phrase(req.client)
    logger.info("POST /generate/%s client=%s", mode, client_slug)

    # Load stored data
    profile = _load_profile_if_exists(client_slug)
    brief_path = Path("clients") / client_slug / "brief.json"
    brief = brief_from_file(str(brief_path)) if brief_path.exists() else None

    if not profile and not brief:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No brief or product profile found for client '{client_slug}'. "
                "Run POST /idea or POST /brain first."
            ),
        )

    # Collect user overrides from request (non-None fields)
    overrides = {}
    for f in ("product", "audience", "pain", "offer", "tone", "cta", "context",
              "icp", "primary_problem", "current_alternative", "desired_outcome",
              "category_frame", "differentiation", "anti_positioning"):
        val = getattr(req, f, None)
        if val is not None and val.strip():
            overrides[f] = val.strip()

    # Build merged generation context: overrides > brain > brief
    # Cross-product detection will suppress stale brief fields automatically
    gen_ctx = build_generation_context(brief=brief, profile=profile, overrides=overrides)

    # If cross-product was detected, include it in the response
    if gen_ctx.cross_product_detected:
        logger.warning("Cross-product detected for client '%s': %s", client_slug, gen_ctx.coherence_notes)

    # Readiness check
    readiness = assess_readiness(gen_ctx, mode)
    if not readiness.ready:
        raise HTTPException(
            status_code=422,
            detail={
                "message": readiness.message,
                "missing_required": readiness.missing_required,
                "missing_recommended": readiness.missing_recommended,
            },
        )

    merged_brief = context_to_brief(gen_ctx)
    brain = gen_ctx.decisions if gen_ctx.decisions else None

    # Build strategy layers
    positioning, narrative = build_strategy_layers(gen_ctx)
    nar_readiness = assess_narrative_readiness(positioning, narrative, mode)

    try:
        final_text, out_path, latest_path = _run_generate(
            merged_brief, mode, client_slug, brain=brain,
            positioning=positioning, narrative=narrative,
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "generation_failed", "detail": str(e)},
        )

    # Extract fixed-schema slots from the blueprint text (no second LLM call).
    slots = None
    if mode == "landing":
        slots = _extract_slots_from_blueprint(final_text)

    # Include brain strength if a profile was loaded
    _strength = _normalize_brain_strength(score_brain_strength(profile)) if profile else None

    result = {
        "mode": mode,
        "text": final_text,
        "slots": slots,
        "brain_strength": _strength,
        "latest_path": str(latest_path),
        "versioned_path": str(out_path),
        "context_sources": gen_ctx.sources,
        "readiness": {
            "ready": readiness.ready,
            "missing_recommended": readiness.missing_recommended,
            "message": readiness.message,
        } if readiness.message else None,
        "narrative_readiness": {
            "ready": nar_readiness.ready,
            "positioning_filled": nar_readiness.positioning_filled,
            "narrative_filled": nar_readiness.narrative_filled,
            "message": nar_readiness.message,
        } if nar_readiness.message else None,
    }
    if gen_ctx.cross_product_detected:
        result["cross_product_warning"] = {
            "detected": True,
            "notes": gen_ctx.coherence_notes,
            "suppressed_fields": [k for k, v in gen_ctx.sources.items() if "suppressed" in v],
        }
    return result
