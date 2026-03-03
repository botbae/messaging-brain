"""Entry point controlling the writing workflow."""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

from agent_loop import (
    run_audit_loop,
    run_audit_mode,
    run_landing_loop,
    run_launch_pack_loop,
    run_linkedin_loop,
    run_positioning_loop,
    run_ux_microcopy_loop,
)
from agents.writing_agent import CriticAgent, StrategistAgent, WritingAgent
from core.brief import build_brief_and_mode
from core.output import next_output_path

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


def run() -> None:
    brief, mode, client_slug, brief_path_used = build_brief_and_mode()
    agent = WritingAgent()

    agent_loop_on = os.getenv("AGENT_LOOP", "").lower() == "true"
    show_strategy = os.getenv("SHOW_STRATEGY", "").lower() == "true"
    _print_execution_banner(mode, client_slug, agent_loop_on)

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
            critic = CriticAgent()
            final_text, meta = run_landing_loop(brief, agent, critic, strategist)
            strategy = meta.get("strategy")

    if show_strategy and strategy:
        final_text = _append_strategy_block(final_text, strategy)

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

    if brief_path_used is not None:
        print(f"Brief: {brief_path_used}")
    print(f"Saved versioned file: {out_path}")
    print(f"Updated latest file: {latest_path}")
    print("Manifest appended.")
    print(f"Output: {out_path}")
    print(f"Latest: {latest_path}")

    open_latest = os.getenv("OPEN_LATEST", "").lower() == "true"
    if open_latest and sys.platform == "darwin":
        # Open the latest output in the default app (macOS)
        subprocess.run(["open", str(latest_path)], check=False)

    print("\n--- GENERATED OUTPUT ---\n")
    print(final_text)
    print("\n--- END OUTPUT ---\n")

if __name__ == "__main__":
    run()
