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
from core.utils import clean_phrase
from main import (
    _load_brain_if_exists,
    _load_profile_if_exists,
    _resolve_brief_from_profile,
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
    return _run_generate_endpoint(req.client, "landing")


@app.post("/generate/ux")
def generate_ux(req: GenerateRequest):
    """Generate a UX pack for the client using their stored brain."""
    return _run_generate_endpoint(req.client, "ux")


@app.post("/generate/positioning")
def generate_positioning(req: GenerateRequest):
    """Generate a positioning document for the client using their stored brain."""
    return _run_generate_endpoint(req.client, "positioning")


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

def _run_generate_endpoint(client: str, mode: str) -> dict:
    client_slug = clean_phrase(client)

    # product_profile.json is the primary source of truth.
    # brief.json is supplementary (cta, examples, context) — it must not dominate.
    profile = _load_profile_if_exists(client_slug)
    brain = profile.decisions if (profile and profile.decisions) else None

    brief_path = Path("clients") / client_slug / "brief.json"
    if brief_path.exists():
        brief = brief_from_file(str(brief_path))
        if profile:
            brief = _resolve_brief_from_profile(brief, profile)
    elif profile:
        # No brief.json yet — construct brief entirely from the saved profile.
        brief = _resolve_brief_from_profile(
            ClientBrief(product="", audience="", pain="", offer="", tone="", cta="", examples="", context=""),
            profile,
        )
    else:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No brief or product profile found for client '{client_slug}'. "
                "Run POST /idea or POST /brain first."
            ),
        )

    final_text, out_path, latest_path = _run_generate(brief, mode, client_slug, brain=brain)

    return {
        "mode": mode,
        "text": final_text,
        "latest_path": str(latest_path),
        "versioned_path": str(out_path),
    }
