"""Thin FastAPI wrapper for the Unimind backend.

Local prototyping only — no auth, no database, no production infra.

Run from the repo root:
    PYTHONPATH=src uvicorn src.api.app:app --reload --port 8000
"""

import sys
from pathlib import Path
from typing import Optional

# Ensure src/ is on the path when uvicorn loads this module from repo root.
_src = Path(__file__).parent.parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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
from core.utils import clean_phrase
from main import (
    _load_profile_if_exists,
    _run_brain_mode,
    _run_generate,
    _run_idea_mode,
)
from product_profile import ProductProfile

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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/idea")
def idea(req: IdeaRequest):
    """Extract ICP, problem, category, and differentiation from a product idea string."""
    client_slug = clean_phrase(req.client) if req.client else None
    result, profile_path = _run_idea_mode(req.idea, client_slug=client_slug)
    if result is None:
        raise HTTPException(status_code=500, detail="Idea extraction failed. Check that Ollama is running.")
    return {
        "client": client_slug or "",
        "idea_extract": result,
        "product_profile_path": str(profile_path) if profile_path else None,
    }


@app.post("/brain")
def brain(req: BrainRequest):
    """Run full positioning LLM pass and save product_profile.json for the client."""
    client_slug = clean_phrase(req.client)
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
    profile, profile_path = _run_brain_mode(brief, client_slug)
    return {
        "client": client_slug,
        "product_profile": profile.to_dict(),
    }


@app.post("/generate/landing")
def generate_landing(req: GenerateRequest):
    """Generate a landing page for the client using their stored brain."""
    return _run_generate_endpoint(req, "landing")


@app.post("/generate/ux")
def generate_ux(req: GenerateRequest):
    """Generate a UX pack for the client using their stored brain."""
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
    return {"client": client_slug, "product_profile": profile.to_dict()}


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _run_generate_endpoint(req: GenerateRequest, mode: str) -> dict:
    client_slug = clean_phrase(req.client)

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
        print(f"API: cross-product detected for client '{client_slug}': {gen_ctx.coherence_notes}")

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

    final_text, out_path, latest_path = _run_generate(
        merged_brief, mode, client_slug, brain=brain,
        positioning=positioning, narrative=narrative,
    )

    result = {
        "mode": mode,
        "text": final_text,
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
