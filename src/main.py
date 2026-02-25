import argparse
import json
import os
from typing import Optional

from writing_agent import ClientBrief, WritingAgent


def _prompt(text: str, default: str = "") -> str:
    label = f"{text}"
    if default:
        label += f" [{default}]"
    label += ": "
    value = input(label).strip()
    return value or default


def _brief_from_file(path: str) -> ClientBrief:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return ClientBrief(
        product=data.get("product", "") or "Product",
        audience=data.get("audience", "") or "Founders, PMs, and operators",
        pain=data.get("pain", "") or "struggling to explain the value clearly",
        offer=data.get("offer", "") or "done-with-you messaging and copywriting",
        tone=data.get("tone", "") or "clear, confident, and human",
        cta=data.get("cta", "") or "Book a short working session.",
        examples=data.get("examples", "") or "",
        context=data.get("context", "") or "",
    )


def _brief_from_env() -> Optional[ClientBrief]:
    product = os.getenv("PRODUCT")
    audience = os.getenv("AUDIENCE")
    pain = os.getenv("PAIN")
    offer = os.getenv("OFFER")
    tone = os.getenv("TONE")
    cta = os.getenv("CTA")
    examples = os.getenv("EXAMPLES", "")
    context = os.getenv("CONTEXT", "")

    if not any([product, audience, pain, offer, tone, cta, examples, context]):
        return None

    return ClientBrief(
        product=product or "Product",
        audience=audience or "Founders, PMs, and operators",
        pain=pain or "struggling to explain the value clearly",
        offer=offer or "done-with-you messaging and copywriting",
        tone=tone or "clear, confident, and human",
        cta=cta or "Book a short working session.",
        examples=examples or "",
        context=context or "",
    )


def _brief_interactive() -> ClientBrief:
    default_product = os.getenv("PRODUCT", "AI writing assistant")

    product = _prompt("Product", default_product)
    audience = _prompt("Audience", "Founders, PMs, and operators")
    pain = _prompt("Main pain you solve", "They struggle to explain the product clearly.")
    offer = _prompt("Primary offer", "Done-with-you messaging and copywriting.")
    tone = _prompt("Tone", "Clear, confident, and human.")
    cta = _prompt("Primary call-to-action", "Book a short working session.")
    examples = _prompt("Examples / inspiration (links or notes, optional)", "")
    context = _prompt("Anything else we should know (optional)", "")

    return ClientBrief(
        product=product,
        audience=audience,
        pain=pain,
        offer=offer,
        tone=tone,
        cta=cta,
        examples=examples,
        context=context,
    )


def _build_brief() -> ClientBrief:
    parser = argparse.ArgumentParser(description="Run the writing agent on a client brief.")
    parser.add_argument(
        "--brief",
        type=str,
        help="Path to a JSON file containing a client brief.",
    )
    args = parser.parse_args()

    if args.brief:
        return _brief_from_file(args.brief)

    env_brief = _brief_from_env()
    if env_brief is not None:
        return env_brief

    return _brief_interactive()


def run() -> str:
    brief = _build_brief()
    agent = WritingAgent()
    return agent.write_landing_page(brief)


if __name__ == "__main__":
    print(run())
