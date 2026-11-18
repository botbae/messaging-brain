"""Every output type should still produce usable text when no model is reachable."""

import pytest

from agents.writing_agent import WritingAgent, score_positioning

DECISIONS = {
    "icp": "seed-stage SaaS founders",
    "primary_problem": "they cannot explain the product",
    "current_alternative": "ChatGPT prompts",
    "desired_outcome": "a clear landing page",
    "category_frame": "messaging tool",
    "differentiation": "works from a structured brief",
    "anti_positioning": "not a generic AI writer",
}

CASES = [
    ("write_landing_page", "HEADLINE"),
    ("write_landing_blueprint", "POSITIONING SUMMARY"),
    ("write_linkedin_post", "HOOK"),
    ("write_ux_microcopy", "ONBOARDING"),
    ("write_ux_pack", "UX CONTEXT"),
    ("write_launch_pack", "TEASER LINE"),
    ("write_positioning", "PRODUCT"),
]


@pytest.mark.parametrize("brain", [None, DECISIONS], ids=["from-brief", "from-brain"])
@pytest.mark.parametrize("method,expected", CASES)
def test_writer_fallback_output(sample_brief, brain, method, expected):
    text = getattr(WritingAgent(brain_decisions=brain), method)(sample_brief)
    assert isinstance(text, str)
    assert expected in text
    assert sample_brief.product.split()[0] in text or method == "write_landing_page"


def test_brain_decisions_skip_extraction(sample_brief):
    agent = WritingAgent(brain_decisions=DECISIONS)
    assert agent.extract_positioning_decisions(sample_brief)["icp"] == DECISIONS["icp"]


def test_score_positioning_returns_score_and_notes(sample_brief):
    text = WritingAgent().write_positioning(sample_brief)
    result = score_positioning(text)
    assert set(result) == {"score", "notes"}
