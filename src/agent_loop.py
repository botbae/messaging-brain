"""Agent loop orchestration for landing, LinkedIn, UX microcopy, launch pack, and audit flows."""

from typing import Dict, Tuple

from agents.writing_agent import (
    ClientBrief,
    CriticAgent,
    StrategistAgent,
    WritingAgent,
    score_positioning,
)


def run_audit_mode(brief: ClientBrief) -> str:
    """Audit-only: use CriticAgent on a minimal draft from the brief. Returns Score + Notes."""
    critic = CriticAgent()
    draft = (
        f"HEADLINE\n{brief.product}\n\nSUBHEAD\nFor {brief.audience}. {brief.pain}"
    )
    critique = critic.review_landing_page(draft, brief)
    lines = [f"Score: {critique.get('score', 'NA')}/10", ""]
    notes = critique.get("notes", [])
    if notes:
        lines.append("Notes:")
        for n in notes:
            lines.append(f"- {n}")
    return "\n".join(lines) + "\n"


def run_landing_loop(
    brief: ClientBrief,
    writer: WritingAgent,
    critic: CriticAgent,
    strategist: StrategistAgent,
) -> Tuple[str, Dict[str, dict]]:
    draft_v1 = writer.write_landing_page(brief)
    critique = critic.review_landing_page(draft_v1, brief)
    strategy = strategist.suggest(brief, draft_v1, critique)

    final = writer.rewrite_landing_page(
        brief,
        draft_v1,
        {**critique, "strategy": strategy, "include_in_output": False},
    )

    return final, {"critique": critique, "strategy": strategy}


def run_linkedin_loop(
    brief: ClientBrief,
    writer: WritingAgent,
    strategist: StrategistAgent,
) -> Tuple[str, Dict[str, dict]]:
    draft = writer.write_linkedin_post(brief)
    strategy = strategist.suggest(brief, draft, None)
    final = writer.rewrite_linkedin_post(brief, draft, strategy)
    return final, {"strategy": strategy}


def run_ux_microcopy_loop(
    brief: ClientBrief,
    writer: WritingAgent,
    strategist: StrategistAgent,
) -> Tuple[str, Dict[str, dict]]:
    draft = writer.write_ux_microcopy(brief)
    strategy = strategist.suggest(brief, draft, None)
    final = writer.rewrite_ux_microcopy(brief, draft, strategy)
    return final, {"strategy": strategy}


def run_launch_pack_loop(
    brief: ClientBrief,
    writer: WritingAgent,
    strategist: StrategistAgent,
) -> Tuple[str, Dict[str, dict]]:
    draft = writer.write_launch_pack(brief)
    strategy = strategist.suggest(brief, draft, None)
    final = writer.rewrite_launch_pack(brief, draft, strategy)
    return final, {"strategy": strategy}


def run_audit_loop(
    brief: ClientBrief,
    critic: CriticAgent,
) -> Tuple[str, Dict[str, dict]]:
    audit_text = run_audit_mode(brief)
    return audit_text, {}


def run_positioning_loop(
    brief: ClientBrief,
    writer: WritingAgent,
) -> Tuple[str, Dict[str, dict]]:
    draft = writer.write_positioning(brief)
    result = score_positioning(draft)
    score = result.get("score", 0)
    notes = result.get("notes", [])
    block = [draft.rstrip(), "", f"POSITIONING SCORE: {score}/10", "NOTES:"]
    for n in notes:
        block.append(f"- {n}")
    return "\n".join(block) + "\n", {}

