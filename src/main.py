"""Entry point controlling the writing workflow."""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from agent_loop import (
    run_audit_loop,
    run_audit_mode,
    run_landing_loop,
    run_launch_pack_loop,
    run_linkedin_loop,
    run_positioning_loop,
    run_ux_microcopy_loop,
)
from agents.writing_agent import CriticAgent, FactGuardAgent, StrategistAgent, WritingAgent
from core.brief import build_brief_and_mode
from core.model_provider import generate as llm_generate
from core.output import next_output_path, slugify
from core.utils import clean_phrase
from product_profile import ProductProfile

MODEL_NAME = "llama3:8b"


def _append_strategy_block(text: str, strategy: dict) -> str:
    if not strategy:
        return text

    lines = [text.rstrip(), "", "STRATEGY (AUTO)"]
    for key in ["positioning", "clarity_fixes", "cta_improvements", "must_include"]:
        items = strategy.get(key) or []
        for item in items:
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _print_execution_banner(mode: str, client_slug: str | None, agent_loop_on: bool) -> None:
    print("====================================")
    print(f"MODE: {mode}")
    print(f"CLIENT: {client_slug or ''}")
    print(f"MODEL: {MODEL_NAME}")
    print(f"AGENT_LOOP: {str(agent_loop_on).lower()}")


def _ensure_output_artifacts(base_dir) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = base_dir / "_manifest.jsonl"
    if not manifest_path.exists():
        manifest_path.touch()


def _idea_to_profile(extract: dict, idea_text: str) -> "ProductProfile":
    """Convert raw idea extraction output to an initial ProductProfile (Messaging Brain seed).

    Fields that need a full brief (current_alternative, desired_outcome, anti_positioning)
    are left blank — run --mode brain with a full brief to fill them in.
    """
    decisions = {
        "icp": extract.get("icp", ""),
        "primary_problem": extract.get("problem", ""),
        "current_alternative": "",
        "desired_outcome": "",
        "category_frame": extract.get("category", ""),
        "differentiation": extract.get("differentiation", ""),
        "anti_positioning": "",
    }
    return ProductProfile(
        product=idea_text.strip()[:120],
        audience=extract.get("icp", ""),
        problem=extract.get("problem", ""),
        alternatives="",
        advantage=extract.get("differentiation", ""),
        tone="",
        goal="",
        context="Seeded from idea extraction. Run --mode brain with a full brief to refine.",
        decisions=decisions,
    )


def _load_brain_if_exists(client_slug: str | None) -> dict | None:
    """Load positioning decisions from clients/<client>/product_profile.json if it exists.

    Returns the decisions dict (non-empty), or None if not found.
    """
    if not client_slug:
        return None
    profile_path = Path("clients") / client_slug / "product_profile.json"
    if not profile_path.exists():
        return None
    profile = ProductProfile.load(profile_path)
    if profile.decisions:
        return profile.decisions
    return None


def _recover_json_object(raw: str) -> str:
    """Best-effort repair of common LLM JSON issues.

    Handles:
    - Extra text before/after the JSON object
    - Missing closing brace
    - Trailing commas before closing brace
    """
    import re as _re
    # Extract the first {...} block (greedy, so we get the outermost one)
    start = raw.find("{")
    if start == -1:
        return raw
    end = raw.rfind("}")
    if end == -1:
        # No closing brace — find the last real value and close it
        candidate = raw[start:].rstrip()
        # Remove trailing comma if present
        candidate = _re.sub(r",\s*$", "", candidate)
        candidate = candidate + "\n}"
    else:
        candidate = raw[start : end + 1]
    # Remove trailing commas before closing brace: {"a": "b",} → {"a": "b"}
    candidate = _re.sub(r",\s*}", "}", candidate)
    return candidate


def _run_idea_mode(idea_text: str, client_slug: str | None = None) -> tuple[dict | None, Path | None]:
    """Extract ICP, problem, category, differentiation from a product idea string.

    If --client is provided:
      - Saves the raw extract to clients/<client>/idea_extract.json
      - Creates an initial product_profile.json (Messaging Brain seed)
      - Run --mode brain with a full brief to refine the brain further

    Returns (result_dict, profile_path) or (None, None) on failure.
    """
    import re
    system = (
        "You are a product positioning analyst. "
        "Respond with ONLY a JSON object — no markdown, no explanation, no trailing text. "
        "Use exactly these four keys: icp, problem, category, differentiation. "
        "Each value must be one short, concrete sentence. "
        "The response must be a complete, valid JSON object ending with }."
    )
    user = (
        f"Product idea: {idea_text}\n\n"
        "Return a complete JSON object with keys: icp, problem, category, differentiation. "
        "Example format:\n"
        '{"icp": "...", "problem": "...", "category": "...", "differentiation": "..."}'
    )
    try:
        raw = llm_generate(system=system, user=user, model=MODEL_NAME, temperature=0.2)
    except Exception as e:
        print(f"Idea extraction failed: {e}")
        return None, None
    if not raw or not raw.strip():
        print("No response from model.")
        return None, None
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```\w*\n?", "", raw)
        raw = re.sub(r"\n?```\s*$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        recovered = _recover_json_object(raw)
        try:
            data = json.loads(recovered)
        except json.JSONDecodeError:
            print("Could not parse JSON after recovery attempt.\nRaw output:\n", raw)
            return None, None
    result = {
        "icp": (data.get("icp") or "").strip(),
        "problem": (data.get("problem") or "").strip(),
        "category": (data.get("category") or "").strip(),
        "differentiation": (data.get("differentiation") or "").strip(),
    }
    print("\n--- IDEA EXTRACTION ---\n")
    print(json.dumps(result, indent=2))
    print("\n--- END ---\n")

    profile_path = None
    if client_slug:
        client_dir = Path("clients") / client_slug
        client_dir.mkdir(parents=True, exist_ok=True)

        extract_path = client_dir / "idea_extract.json"
        with open(extract_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"Saved idea extract: {extract_path}")

        profile = _idea_to_profile(result, idea_text)
        profile_path = client_dir / "product_profile.json"
        profile.save(profile_path)
        print(f"Created initial brain: {profile_path}")
        print("Run --mode brain with a full brief to refine the brain.")

    return result, profile_path


def _run_brain_mode(brief, client_slug: str | None) -> tuple["ProductProfile", Path]:
    """Load brief, extract positioning decisions, save to product_profile.json; print result.

    Returns (profile, profile_path).
    """
    agent = WritingAgent()
    decisions = agent.extract_positioning_decisions(brief)
    profile = ProductProfile(
        product=clean_phrase(brief.product) or "",
        audience=clean_phrase(brief.audience) or "",
        problem=(brief.pain or "").strip(),
        alternatives=(decisions.get("current_alternative") or "").strip(),
        advantage=clean_phrase(brief.offer) or "",
        tone=(brief.tone or "").strip(),
        goal=(decisions.get("desired_outcome") or "").strip(),
        context=(brief.context or "").strip(),
        decisions=decisions,
    )
    client_dir = client_slug or slugify(brief.product or "product")
    profile_path = Path("clients") / client_dir / "product_profile.json"
    profile.save(profile_path)
    print(f"Saved: {profile_path}")
    print("\n--- BRAIN (product_profile) ---\n")
    print(json.dumps(profile.to_dict(), indent=2))
    print("\n--- END ---\n")
    return profile, profile_path


def _run_generate(
    brief,
    mode: str,
    client_slug: str | None,
    brain: dict | None = None,
    agent_loop_on: bool = False,
    show_strategy: bool = False,
    brief_path_used: Path | None = None,
) -> tuple[str, Path, Path]:
    """Dispatch to the correct agent, save output files, and return (final_text, out_path, latest_path)."""
    agent = WritingAgent()
    if brain:
        agent.brain_decisions = brain

    if not agent_loop_on:
        if mode == "landing":
            draft_v1 = agent.write_landing_page(brief)
            critic = CriticAgent()
            critique = critic.review_landing_page(draft_v1, brief)
            final_text = agent.rewrite_landing_page(brief, draft_v1, critique)
            strategy = None
        elif mode == "linkedin":
            final_text = agent.write_linkedin_post(brief)
            strategy = None
        elif mode == "ux_microcopy":
            final_text = agent.write_ux_microcopy(brief)
            strategy = None
        elif mode == "launch_pack":
            final_text = agent.write_launch_pack(brief)
            strategy = None
        elif mode == "audit":
            final_text = run_audit_mode(brief)
            strategy = None
        elif mode == "positioning":
            agent.extract_positioning_decisions(brief)
            final_text = agent.write_positioning(brief)
            strategy = None
        elif mode == "ux":
            final_text = agent.write_ux_pack(brief, target="product")
            strategy = None
        elif mode == "ux_operator":
            final_text = agent.write_ux_pack(brief, target="operator")
            strategy = None
        elif mode == "ux_product":
            final_text = agent.write_ux_pack(brief, target="product")
            strategy = None
        else:
            final_text = agent.write_landing_page(brief)
            strategy = None
    else:
        strategist = StrategistAgent()
        if mode == "landing":
            critic = CriticAgent()
            final_text, meta = run_landing_loop(brief, agent, critic, strategist)
            strategy = meta.get("strategy")
        elif mode == "linkedin":
            final_text, meta = run_linkedin_loop(brief, agent, strategist)
            strategy = meta.get("strategy")
        elif mode == "ux_microcopy":
            final_text, meta = run_ux_microcopy_loop(brief, agent, strategist)
            strategy = meta.get("strategy")
        elif mode == "launch_pack":
            final_text, meta = run_launch_pack_loop(brief, agent, strategist)
            strategy = meta.get("strategy")
        elif mode == "audit":
            critic = CriticAgent()
            final_text, meta = run_audit_loop(brief, critic)
            strategy = meta.get("strategy")
        elif mode == "positioning":
            agent.extract_positioning_decisions(brief)
            final_text, meta = run_positioning_loop(brief, agent)
            strategy = meta.get("strategy")
        elif mode in ("ux", "ux_product"):
            final_text = agent.write_ux_pack(brief, target="product")
            strategy = None
        elif mode == "ux_operator":
            final_text = agent.write_ux_pack(brief, target="operator")
            strategy = None
        else:
            critic = CriticAgent()
            final_text, meta = run_landing_loop(brief, agent, critic, strategist)
            strategy = meta.get("strategy")

    if show_strategy and strategy:
        final_text = _append_strategy_block(final_text, strategy)

    final_text = FactGuardAgent().clean(final_text, brief)
    final_text = final_text.rstrip("\n") + "\n"

    out_path = next_output_path(brief.product, mode, client_slug)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(final_text)

    base_dir = out_path.parent
    _ensure_output_artifacts(base_dir)
    latest_path = base_dir / f"{mode}_latest.md"
    with open(latest_path, "w", encoding="utf-8") as f:
        f.write(final_text)

    manifest_path = base_dir / "_manifest.jsonl"
    manifest_entry = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "client": client_slug or "",
        "mode": mode,
        "brief_path": str(brief_path_used) if brief_path_used is not None else "",
        "output_path": str(out_path),
        "latest_path": str(latest_path),
        "model_used": MODEL_NAME,
        "agent_loop": agent_loop_on,
    }
    with open(manifest_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(manifest_entry) + "\n")

    return final_text, out_path, latest_path


def run() -> None:
    brief, mode, client_slug, brief_path_used, idea_text = build_brief_and_mode()

    if mode == "idea":
        if not idea_text:
            print("--mode idea requires --idea <text>")
            sys.exit(1)
        _print_execution_banner(mode, client_slug, False)
        _run_idea_mode(idea_text, client_slug=client_slug)
        return

    if mode == "brain":
        _print_execution_banner(mode, client_slug, False)
        _run_brain_mode(brief, client_slug)
        return

    # Load the Messaging Brain (product_profile.json) if it exists for this client.
    # When present, the agent uses pre-extracted decisions instead of re-running the LLM
    # decision phase — brief still provides raw context for fallbacks and fact-grounding.
    brain = _load_brain_if_exists(client_slug)
    if brain:
        print(f"Brain loaded: clients/{client_slug}/product_profile.json")

    agent_loop_on = os.getenv("AGENT_LOOP", "").lower() == "true"
    show_strategy = os.getenv("SHOW_STRATEGY", "").lower() == "true"
    _print_execution_banner(mode, client_slug, agent_loop_on)

    final_text, out_path, latest_path = _run_generate(
        brief, mode, client_slug,
        brain=brain,
        agent_loop_on=agent_loop_on,
        show_strategy=show_strategy,
        brief_path_used=brief_path_used,
    )

    if brief_path_used is not None:
        print(f"Brief: {brief_path_used}")
    print(f"Saved versioned file: {out_path}")
    print(f"Updated latest file: {latest_path}")
    print("Manifest appended.")
    print(f"Output: {out_path}")
    print(f"Latest: {latest_path}")

    open_latest = os.getenv("OPEN_LATEST", "").lower() == "true"
    if open_latest and sys.platform == "darwin":
        subprocess.run(["open", str(latest_path)], check=False)

    print("\n--- GENERATED OUTPUT ---\n")
    print(final_text)
    print("\n--- END OUTPUT ---\n")

if __name__ == "__main__":
    run()
