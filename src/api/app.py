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
from pydantic import BaseModel

from agents.writing_agent import ClientBrief
from core.brief import brief_from_file
from core.utils import clean_phrase
from main import _load_brain_if_exists, _run_brain_mode, _run_generate, _run_idea_mode

app = FastAPI(
    title="Unimind API",
    description="Local prototyping API — not for production use.",
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class IdeaRequest(BaseModel):
    idea: str
    client: Optional[str] = None


class BriefData(BaseModel):
    product: str = "Product"
    audience: str = "Founders, PMs, and operators"
    pain: str = ""
    offer: str = ""
    tone: str = "clear, confident, and human"
    cta: str = ""
    context: str = ""
    examples: str = ""


class BrainRequest(BaseModel):
    client: str
    brief: BriefData


class GenerateRequest(BaseModel):
    client: str


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


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _run_generate_endpoint(client: str, mode: str) -> dict:
    client_slug = clean_phrase(client)

    brief_path = Path("clients") / client_slug / "brief.json"
    if not brief_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No brief found at {brief_path}. Run POST /brain first to create one.",
        )

    brief = brief_from_file(str(brief_path))
    brain = _load_brain_if_exists(client_slug)

    final_text, out_path, latest_path = _run_generate(brief, mode, client_slug, brain=brain)

    return {
        "mode": mode,
        "text": final_text,
        "latest_path": str(latest_path),
        "versioned_path": str(out_path),
    }
