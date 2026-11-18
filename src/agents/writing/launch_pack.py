"""Launch pack writer: LaunchPackWriterMixin.

Split out of agents/writing_agent.py; import from there for a stable API.
"""

from core.utils import clean_phrase, lower_first
from agents.writing.common import ClientBrief


class LaunchPackWriterMixin:
    """Launch pack generation.

    Mixed into WritingAgent; methods rely on its fields (brain_decisions,
    positioning, narrative) and may call methods from the other mixins.
    """

    def write_launch_pack(self, brief: ClientBrief) -> str:
        """Generate launch pack: teaser, social post, 5-tweet thread, app store subtitle."""
        product = clean_phrase(brief.product) or "Your product"
        audience = clean_phrase(brief.audience) or "your audience"
        audience = lower_first(audience)
        offer_phrase = lower_first(clean_phrase(brief.offer) or "the outcome they need")

        teaser = f"{product} — for {audience} who want {offer_phrase}."
        social = (
            f"We built {product} for {audience}. "
            f"It's built around one thing: {offer_phrase}. "
            "If that's you, we'd love your feedback."
        )
        thread = [
            f"1. {product} is for {audience}.",
            f"2. The problem: most tools don't help you {offer_phrase}.",
            f"3. We focused on one outcome: get from brief to clear message fast.",
            "4. No fluff. No generic templates. Just your story, sharp.",
            f"5. If that resonates, try {product}. Link in bio.",
        ]
        app_store = f"{product}: {offer_phrase} for {audience}."

        body = f"""TEASER LINE
{teaser}

SOCIAL POST
{social}

5-TWEET THREAD
{chr(10).join(thread)}

APP STORE SUBTITLE
{app_store}
"""
        return (body.rstrip("\n") + "\n")

    def rewrite_launch_pack(self, brief: ClientBrief, draft: str, strategy: dict) -> str:
        """Rule-based pass: keep structure and headers; no reorder."""
        if not draft or not strategy:
            return draft
        return draft
