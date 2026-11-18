"""Thin FastAPI wrapper for the Messaging Brain backend.

Local prototyping only — no auth, no database, no production infra.

Run from the repo root:
    PYTHONPATH=src uvicorn src.api.app:app --reload --port 8000

Interactive docs: http://localhost:8000/docs
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
from pydantic import BaseModel, ConfigDict

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
from core.utils import clean_phrase, is_safe_client_slug
from main import (
    _load_profile_if_exists,
    _run_brain_mode,
    _run_generate,
    _run_idea_mode,
)
from product_profile import ProductProfile, score_brain_strength, suggest_brain_improvements

app = FastAPI(
    title="Messaging Brain API",
    description="Local prototyping API — not for production use.",
    version="0.1.0",
)

def _client_slug(raw: Optional[str]) -> str:
    """Clean a client name and reject anything that is not a plain folder name."""
    slug = clean_phrase(raw)
    if not is_safe_client_slug(slug):
        raise HTTPException(
            status_code=400,
            detail="client must be 1-64 letters, digits, '-' or '_' (no spaces, dots or slashes)",
        )
    return slug


# Local frontend prototyping — allow Next.js dev server to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    """Messaging brain fields from POST /brain/save.

    Canonical keys match the frontend IdeaExtract. Legacy aliases are merged so
    old clients (icp/category/differentiation/current_alternative) keep working.
    Use Optional so omitted JSON keys do not overwrite stored values; explicit
    empty strings clear fields.
    """

    model_config = ConfigDict(extra="ignore")

    # Canonical (frontend IdeaExtract)
    product: Optional[str] = None
    audience: Optional[str] = None
    problem: Optional[str] = None
    alternatives: Optional[str] = None
    advantage: Optional[str] = None
    tone: Optional[str] = None
    goal: Optional[str] = None
    context: Optional[str] = None
    # Legacy aliases
    icp: Optional[str] = None
    category: Optional[str] = None
    differentiation: Optional[str] = None
    current_alternative: Optional[str] = None
    alternative: Optional[str] = None


class BrainSaveRequest(BaseModel):
    client: str
    idea_extract: IdeaExtractData


class ClientInitRequest(BaseModel):
    client: str
    reset_brief: bool = False


class BundleRequest(BaseModel):
    client: str


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


def _idea_extract_canonical_response(profile: ProductProfile) -> dict:
    """Echo saved brain in frontend IdeaExtract shape."""
    return {
        "product": profile.product or "",
        "audience": profile.audience or "",
        "problem": profile.problem or "",
        "alternatives": profile.alternatives or "",
        "advantage": profile.advantage or "",
        "tone": profile.tone or "",
        "goal": profile.goal or "",
        "context": profile.context or "",
    }


def _apply_idea_extract_to_profile(profile: ProductProfile, edits: IdeaExtractData) -> None:
    """Apply save payload to ProductProfile; sync top-level fields with decisions dict."""

    if edits.product is not None:
        profile.product = edits.product.strip()

    # audience <-> icp (canonical audience wins)
    audience_src = edits.audience if edits.audience is not None else edits.icp
    if audience_src is not None:
        s = audience_src.strip()
        profile.audience = s
        profile.decisions["icp"] = s

    if edits.problem is not None:
        s = edits.problem.strip()
        profile.problem = s
        profile.decisions["primary_problem"] = s

    # alternatives <-> current_alternative; legacy "alternative" from some extracts
    alt_src = edits.alternatives
    if alt_src is None:
        alt_src = edits.current_alternative
    if alt_src is None:
        alt_src = edits.alternative
    if alt_src is not None:
        s = alt_src.strip()
        profile.alternatives = s
        profile.decisions["current_alternative"] = s

    # advantage <-> differentiation (canonical advantage wins)
    adv_src = edits.advantage if edits.advantage is not None else edits.differentiation
    if adv_src is not None:
        s = adv_src.strip()
        profile.advantage = s
        profile.decisions["differentiation"] = s

    if edits.tone is not None:
        s = edits.tone.strip()
        profile.tone = s
        profile.decisions["tone"] = s

    if edits.goal is not None:
        s = edits.goal.strip()
        profile.goal = s
        profile.decisions["desired_outcome"] = s

    if edits.context is not None:
        profile.context = edits.context.strip()

    # Legacy category → category_frame; mirror to context when context not sent (QA / old clients)
    if edits.category is not None:
        s = edits.category.strip()
        profile.decisions["category_frame"] = s
        if edits.context is None:
            profile.context = s


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
    client_slug = _client_slug(req.client) if req.client else None
    logger.info("POST /idea client=%s", client_slug or "(anonymous)")
    result, profile_path = _run_idea_mode(req.idea, client_slug=client_slug)
    if result is None:
        raise HTTPException(status_code=500, detail="Idea extraction failed. Check that Ollama is running.")

    brain_suggestions = None
    brain_strength = None
    confidence_report = None
    if profile_path and Path(profile_path).exists():
        _profile = ProductProfile.load(profile_path)
        _suggestions = suggest_brain_improvements(_profile)
        if _suggestions:
            brain_suggestions = _suggestions
        brain_strength = _normalize_brain_strength(score_brain_strength(_profile))
        try:
            from core.confidence_engine import score_decision_state
            confidence_report = score_decision_state(_profile, client_slug or "").model_dump()
        except Exception:
            pass

    return {
        "client": client_slug or "",
        "suggested_slug": result.get("suggested_slug", ""),
        "idea_extract": result,
        "brain_suggestions": brain_suggestions,
        "brain_strength": brain_strength,
        "confidence_report": confidence_report,
    }


@app.post("/brain")
def brain(req: BrainRequest):
    """Run full positioning LLM pass and save product_profile.json for the client."""
    client_slug = _client_slug(req.client)
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
    confidence_report = None
    try:
        from core.confidence_engine import score_decision_state
        confidence_report = score_decision_state(profile, client_slug).model_dump()
    except Exception:
        pass
    return {
        "client": client_slug,
        "product_profile": _safe_profile(profile),
        "brain_suggestions": _brain_suggestions if _brain_suggestions else None,
        "brain_strength": _brain_strength,
        "confidence_report": confidence_report,
    }


@app.post("/client/init")
def client_init(req: ClientInitRequest):
    """Initialize or reset a client directory.

    Removes brain, idea extract, and output files for a fresh start.
    Optionally invalidates an existing brief (reset_brief=true).
    """
    client_slug = _client_slug(req.client)
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


def generate_bundle_alias(req: BundleRequest):
    """Alias for /generate/bundle registered before the {mode} catch-all."""
    return generate_bundle(req)


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
    client_slug = _client_slug(client)
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

    Canonical idea_extract keys match the frontend IdeaExtract (product, audience,
    problem, alternatives, advantage, tone, goal, context). Legacy keys (icp,
    category, differentiation, current_alternative, alternative) are merged:
      audience / icp → profile.audience + decisions.icp
      advantage / differentiation → profile.advantage + decisions.differentiation
      alternatives / current_alternative / alternative → profile.alternatives +
        decisions.current_alternative
    Omitted keys leave existing values unchanged; explicit empty strings clear fields.
    """
    client_slug = _client_slug(req.client)
    profile_path = Path("clients") / client_slug / "product_profile.json"

    if not profile_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No product_profile.json found at {profile_path}. Run POST /brain first.",
        )

    profile = ProductProfile.load(profile_path)

    _apply_idea_extract_to_profile(profile, req.idea_extract)

    profile.save(profile_path)
    logger.info("POST /brain/save client=%s — profile updated", client_slug)

    _suggestions = suggest_brain_improvements(profile)
    _strength = _normalize_brain_strength(score_brain_strength(profile))
    return {
        "client": client_slug,
        "product_profile": _safe_profile(profile),
        "idea_extract": _idea_extract_canonical_response(profile),
        "brain_suggestions": _suggestions if _suggestions else None,
        "brain_strength": _strength,
    }


@app.get("/client/{slug}/confidence")
def get_confidence(slug: str):
    """Return the confidence report for a client's brain.

    Loads the saved report from clients/<slug>/confidence_report.json.
    If no saved report exists, scores the current brain on the fly and returns it.
    Returns 404 if the client has no brain at all.
    """
    from core.confidence_engine import load_confidence_report, save_confidence_report, score_decision_state

    client_slug = _client_slug(slug)
    logger.info("GET /client/%s/confidence", client_slug)

    # Try saved report first (fast path)
    report = load_confidence_report(client_slug)
    if report is not None:
        return report.model_dump()

    # Fall back to scoring on the fly
    profile = _load_profile_if_exists(client_slug)
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail=f"No brain found for client '{client_slug}'. Run POST /idea or POST /brain first.",
        )

    report = score_decision_state(profile, client_slug)
    save_confidence_report(report, client_slug)
    return report.model_dump()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Schema-population helpers for /generate/bundle (TASK 3)
# ---------------------------------------------------------------------------

def _profile_to_decision_state(profile: ProductProfile, client_slug: str) -> dict:
    """Build a DecisionState dict from a ProductProfile for the bundle response."""
    from schemas.decision_state import DecisionState
    return DecisionState(
        product=profile.product or "",
        audience=profile.audience or "",
        problem=profile.problem or "",
        alternatives=profile.alternatives or "",
        advantage=profile.advantage or "",
        tone=profile.tone or "",
        goal=profile.goal or "",
        context=profile.context or "",
        decisions=dict(profile.decisions) if profile.decisions else {},
        client_name=client_slug,
        brain_version=getattr(profile, "brain_version", 0) or 0,
        last_saved_at=getattr(profile, "updated_at", "") or "",
        source_idea=getattr(profile, "source_idea", "") or "",
        overall_confidence=0.5,
        generation_safe=True,
    ).model_dump()


def _parse_positioning_doc(text: str, client_slug: str, now: str) -> dict:
    """Parse positioning markdown into a PositioningDoc dict. Falls back to raw_markdown."""
    from schemas.positioning_doc import PositioningDoc, PositioningSection
    import re as _re

    def _extract_section(header: str, all_headers: list[str], src: str) -> str:
        idx = src.find(header)
        if idx < 0:
            return ""
        start = idx + len(header)
        end = len(src)
        for h in all_headers:
            if h == header:
                continue
            hi = src.find(h, start)
            if 0 < hi < end:
                end = hi
        return src[start:end].strip()

    _HEADERS = [
        "PRODUCT", "ICP", "CORE PROBLEM", "CURRENT ALTERNATIVE",
        "WHY CURRENT OPTIONS FAIL", "DESIRED OUTCOME", "CATEGORY FRAME",
        "DIFFERENTIATION", "ANTI-POSITIONING", "POSITIONING STATEMENT", "MESSAGING NOTES",
    ]

    def _sec(header: str) -> Optional[PositioningSection]:
        body = _extract_section(header, _HEADERS, text)
        if not body:
            return None
        return PositioningSection(title=header.title(), content=body)

    try:
        doc = PositioningDoc(
            client_name=client_slug,
            generated_at=now,
            value_proposition=_sec("POSITIONING STATEMENT") or _sec("PRODUCT"),
            icp=_sec("ICP"),
            problem_frame=_sec("CORE PROBLEM"),
            differentiation=_sec("DIFFERENTIATION"),
            category_frame=_sec("CATEGORY FRAME"),
            tone_voice=_sec("MESSAGING NOTES"),
            desired_outcome=_sec("DESIRED OUTCOME"),
            extra_sections=[
                s for s in [_sec("CURRENT ALTERNATIVE"), _sec("WHY CURRENT OPTIONS FAIL"), _sec("ANTI-POSITIONING")]
                if s is not None
            ],
            raw_markdown=text,
        )
        return doc.model_dump()
    except Exception:
        from schemas.positioning_doc import PositioningDoc
        return PositioningDoc(client_name=client_slug, generated_at=now, raw_markdown=text).model_dump()


def _parse_landing_content(text: str, client_slug: str, now: str) -> dict:
    """Parse landing page markdown into a LandingPageContent dict."""
    from schemas.landing_page_content import LandingPageContent, LandingSection, CTAButton

    def _section_body(header: str, next_headers: list[str], src: str) -> str:
        idx = src.find(header)
        if idx < 0:
            return ""
        start = idx + len(header)
        end = len(src)
        for h in next_headers:
            hi = src.find(h, start)
            if 0 < hi < end:
                end = hi
        return src[start:end].strip()

    _H = [
        "HEADLINE", "SUBHEADLINE", "WHAT THIS IS", "WHO IT IS FOR",
        "THE PROBLEM", "WHY EXISTING TOOLS FAIL", "HOW IT WORKS",
        "KEY BENEFITS", "CALL TO ACTION",
        # blueprint variant headers
        "POSITIONING SUMMARY", "HERO", "PROBLEM SECTION",
        "WHY CURRENT OPTIONS FAIL", "PRODUCT EXPLANATION",
        "HOW IT WORKS", "PROOF / CREDIBILITY", "FINAL CTA SECTION",
    ]

    def _field(label: str, src: str) -> str:
        import re as _re
        m = _re.search(rf'{_re.escape(label)}\s*[:\n]\s*(.+)', src, _re.IGNORECASE)
        return m.group(1).strip().strip('"\'') if m else ""

    try:
        headline = _field("Headline", text) or _field("HEADLINE", text)
        subhead = _field("Subhead", text) or _field("SUBHEADLINE", text)
        cta_label = _field("Primary CTA", text) or _field("CALL TO ACTION", text)

        sections = []
        if headline:
            sections.append(LandingSection(
                id="hero", name="Hero",
                headline=headline,
                subheadline=subhead or None,
                cta_buttons=[CTAButton(label=cta_label)] if cta_label else [],
            ))
        problem_body = _section_body("THE PROBLEM", _H, text) or _section_body("PROBLEM SECTION", _H, text)
        if problem_body:
            sections.append(LandingSection(id="problem", name="Problem", body=problem_body))
        solution_body = _section_body("WHAT THIS IS", _H, text) or _section_body("PRODUCT EXPLANATION", _H, text)
        if solution_body:
            sections.append(LandingSection(id="solution", name="Solution", body=solution_body))
        how_body = _section_body("HOW IT WORKS", _H, text)
        if how_body:
            sections.append(LandingSection(id="how_it_works", name="How It Works", body=how_body))

        doc = LandingPageContent(
            client_name=client_slug,
            product="",
            generated_at=now,
            sections=sections,
            raw_markdown=text,
        )
        return doc.model_dump()
    except Exception:
        from schemas.landing_page_content import LandingPageContent
        return LandingPageContent(client_name=client_slug, generated_at=now, raw_markdown=text).model_dump()


def _parse_ux_copy_map(text: str, client_slug: str, now: str) -> dict:
    """Parse UX microcopy markdown into a UXCopyMap dict."""
    from schemas.ux_copy_map import UXCopyMap, UXScreen, UXCopyState

    _UX_HEADERS = ["UX CONTEXT", "ONBOARDING", "EMPTY STATE", "ERROR", "TOAST", "BUTTON LABELS"]

    def _section_body(header: str, src: str) -> str:
        idx = src.find(header)
        if idx < 0:
            return ""
        start = idx + len(header)
        end = len(src)
        for h in _UX_HEADERS:
            if h == header:
                continue
            hi = src.find(h, start)
            if 0 < hi < end:
                end = hi
        return src[start:end].strip()

    try:
        screens = []
        state_map = {
            "ONBOARDING": "onboarding",
            "EMPTY STATE": "empty",
            "ERROR": "error",
            "TOAST": "success",
        }
        for header, state_key in state_map.items():
            body = _section_body(header, text)
            if body:
                screens.append(UXScreen(
                    id=header.lower().replace(" ", "_"),
                    name=header.title(),
                    states=[UXCopyState(state=state_key, body=body)],
                ))

        button_body = _section_body("BUTTON LABELS", text)
        global_labels: dict = {}
        if button_body:
            import re as _re
            for m in _re.finditer(r'[-•]\s*(.+?):\s*(.+)', button_body):
                global_labels[m.group(1).strip().lower()] = m.group(2).strip()

        doc = UXCopyMap(
            client_name=client_slug,
            product="",
            generated_at=now,
            screens=screens,
            global_labels=global_labels,
            raw_markdown=text,
        )
        return doc.model_dump()
    except Exception:
        from schemas.ux_copy_map import UXCopyMap
        return UXCopyMap(client_name=client_slug, generated_at=now, raw_markdown=text).model_dump()


def _save_bundle_artifact(client_slug: str, filename: str, data: dict) -> None:
    """Write a JSON artifact to clients/<slug>/<filename>."""
    import json as _json
    client_dir = Path("clients") / client_slug
    client_dir.mkdir(parents=True, exist_ok=True)
    out = client_dir / filename
    with open(out, "w", encoding="utf-8") as f:
        _json.dump(data, f, indent=2)


def generate_bundle(req: BundleRequest):
    """Run the full artifact pipeline for a client and return an ArtifactBundle.

    Steps:
      1. Load ProductProfile (brain must exist — run POST /brain first)
      2. Score confidence (load saved report or score on-the-fly)
      3. StructuringAgent → LandingPageIA  (saved as landing_ia.json)
      4. _run_generate for positioning, landing, ux  (each saved as versioned .md)
      5. Return ArtifactBundle as JSON  (also saved as artifact_bundle.json)

    Non-fatal errors in any step are captured in bundle.errors — the rest of
    the pipeline continues.
    """
    import uuid as _uuid
    from datetime import datetime, timezone
    from agents.structuring_agent import StructuringAgent
    from schemas.artifact_bundle import ArtifactBundle, ArtifactMeta

    client_slug = _client_slug(req.client)
    if not client_slug:
        raise HTTPException(status_code=400, detail="client is required")
    logger.info("POST /generate/bundle client=%s", client_slug)

    # -- Load brain --------------------------------------------------------
    profile = _load_profile_if_exists(client_slug)
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No brain found for client '{client_slug}'. "
                "Run POST /idea or POST /brain first."
            ),
        )

    # -- Confidence report -------------------------------------------------
    confidence_report = None
    try:
        from core.confidence_engine import (
            load_confidence_report,
            save_confidence_report,
            score_decision_state,
        )
        confidence_report = load_confidence_report(client_slug)
        if confidence_report is None:
            confidence_report = score_decision_state(profile, client_slug)
            save_confidence_report(confidence_report, client_slug)
    except Exception as _e:
        logger.warning("bundle: confidence scoring failed — %s", _e)

    # -- Bundle shell ------------------------------------------------------
    now = datetime.now(timezone.utc).isoformat()
    bundle_id = f"{client_slug}_{now[:19].replace(':', '-').replace('T', '_')}"
    from core.model_provider import active_provider_name
    provider_used = active_provider_name()

    bundle = ArtifactBundle(
        client_name=client_slug,
        bundle_id=bundle_id,
        created_at=now,
        confidence_report=confidence_report,
    )

    # -- TASK 3: decision_state from ProfileProfile (always available) -----
    try:
        bundle.decision_state = _profile_to_decision_state(profile, client_slug)
    except Exception as _e:
        bundle.errors.append(f"decision_state: {_e}")
        logger.warning("bundle: decision_state failed — %s", _e)

    # -- Step 1: Landing IA via StructuringAgent ---------------------------
    try:
        ia = StructuringAgent().run(profile, confidence_report)
        ia["client"] = client_slug
        bundle.landing_page_ia = ia
        bundle.artifact_meta.append(ArtifactMeta(
            artifact_type="landing_page_ia",
            generated_at=now,
            generation_mode="ia",
            provider_used=provider_used,
        ))
        _save_bundle_artifact(client_slug, "landing_ia.json", ia)
        logger.info("bundle: landing_ia generated for %s", client_slug)
    except Exception as _e:
        bundle.errors.append(f"landing_ia: {_e}")
        logger.warning("bundle: landing_ia failed — %s", _e)

    # -- Steps 2-4: positioning + landing + ux via existing pipeline -------
    brief_path = Path("clients") / client_slug / "brief.json"
    brief = brief_from_file(str(brief_path)) if brief_path.exists() else None
    gen_ctx = build_generation_context(brief=brief, profile=profile)
    brain = gen_ctx.decisions if gen_ctx.decisions else None
    merged_brief = context_to_brief(gen_ctx)
    positioning_ctx, narrative_ctx = build_strategy_layers(gen_ctx)

    for mode in ("positioning", "landing", "ux"):
        try:
            text, out_path, _ = _run_generate(
                merged_brief, mode, client_slug,
                brain=brain,
                positioning=positioning_ctx,
                narrative=narrative_ctx,
            )
            bundle.raw_outputs[mode] = text
            bundle.artifact_meta.append(ArtifactMeta(
                artifact_type=mode,
                generated_at=now,
                generation_mode=mode,
                provider_used=provider_used,
                output_path=str(out_path),
            ))
            logger.info("bundle: %s generated for %s", mode, client_slug)
        except Exception as _e:
            bundle.errors.append(f"{mode}: {_e}")
            logger.warning("bundle: %s failed — %s", mode, _e)

    # -- TASK 3: populate structured schema fields from raw_outputs ---------
    positioning_text = bundle.raw_outputs.get("positioning", "")
    landing_text = bundle.raw_outputs.get("landing", "")
    ux_text = bundle.raw_outputs.get("ux", "")

    if positioning_text:
        try:
            bundle.positioning_doc = _parse_positioning_doc(positioning_text, client_slug, now)
        except Exception as _e:
            bundle.errors.append(f"positioning_doc: {_e}")
            logger.warning("bundle: positioning_doc parse failed — %s", _e)

    if landing_text:
        try:
            bundle.landing_page_content = _parse_landing_content(landing_text, client_slug, now)
        except Exception as _e:
            bundle.errors.append(f"landing_page_content: {_e}")
            logger.warning("bundle: landing_page_content parse failed — %s", _e)

    if ux_text:
        try:
            bundle.ux_copy_map = _parse_ux_copy_map(ux_text, client_slug, now)
        except Exception as _e:
            bundle.errors.append(f"ux_copy_map: {_e}")
            logger.warning("bundle: ux_copy_map parse failed — %s", _e)

    # -- TASK 2: quality layer — CriticAgent + StrategistAgent on landing --
    if landing_text and merged_brief:
        from agents.critic_agent import CriticAgent
        from agents.strategist_agent import StrategistAgent

        try:
            critique = CriticAgent().review_landing_page(landing_text, merged_brief)
            # Strip internal flag before exposing to API consumers
            bundle.critic_issues = {
                "score": critique["score"],
                "flags": critique["flags"],
                "notes": critique["notes"],
            }
            logger.info("bundle: critic ran for %s — score %s", client_slug, critique["score"])
        except Exception as _e:
            bundle.errors.append(f"critic: {_e}")
            logger.warning("bundle: critic failed — %s", _e)
            critique = None

        try:
            bundle.recommendations = StrategistAgent().suggest(
                merged_brief, landing_text, critique
            )
            logger.info("bundle: strategist ran for %s", client_slug)
        except Exception as _e:
            bundle.errors.append(f"strategist: {_e}")
            logger.warning("bundle: strategist failed — %s", _e)

    # -- Persist and return ------------------------------------------------
    try:
        _save_bundle_artifact(client_slug, "artifact_bundle.json", bundle.model_dump())
    except Exception as _e:
        bundle.errors.append(f"bundle_save: {_e}")

    return bundle.model_dump()


def _run_generate_endpoint(req: GenerateRequest, mode: str) -> dict:
    client_slug = _client_slug(req.client)
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

    if mode == "landing":
        return {"client": client_slug, "text": final_text}

    # Include brain strength if a profile was loaded
    _strength = _normalize_brain_strength(score_brain_strength(profile)) if profile else None

    result = {
        "mode": mode,
        "text": final_text,
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
