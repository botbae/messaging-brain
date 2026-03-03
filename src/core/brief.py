"""Brief loading: file/env/interactive and client sessions."""

import argparse
import json
import os
from pathlib import Path
from typing import Optional, Tuple

from agents.writing_agent import ClientBrief
from .utils import clean_phrase


def prompt(text: str, default: str = "") -> str:
    label = f"{text}"
    if default:
        label += f" [{default}]"
    label += ": "
    value = input(label).strip()
    return value or default


def brief_from_file(path: str) -> ClientBrief:
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


def brief_from_env() -> Optional[ClientBrief]:
    product = os.getenv("PRODUCT")
    audience = os.getenv("AUDIENCE")
    pain = os.getenv("PAIN")
    offer = os.getenv("OFFER")
    tone = os.getenv("TONE")
    cta = os.getenv("CTA")
    examples = os.getenv("EXAMPLES", "")
    context = os.getenv("CONTEXT", "")

    # Only treat env vars as a brief if at least one of the required
    # core fields is provided. Optional fields alone should not bypass
    # the interactive prompt flow.
    if not any([product, audience, pain, offer, tone, cta]):
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


def brief_interactive() -> ClientBrief:
    default_product = os.getenv("PRODUCT", "AI writing assistant")

    product = prompt("Product", default_product)
    audience = prompt("Audience", "Founders, PMs, and operators")
    pain = prompt("Main pain you solve", "They struggle to explain the product clearly.")
    offer = prompt("Primary offer", "Done-with-you messaging and copywriting.")
    tone = prompt("Tone", "Clear, confident, and human.")
    cta = prompt("Primary call-to-action", "Book a short working session.")
    examples = prompt("Examples / inspiration (links or notes, optional)", "")
    context = prompt("Anything else we should know (optional)", "")

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


def build_brief_and_mode() -> Tuple[ClientBrief, str, Optional[str], Optional[Path]]:
    parser = argparse.ArgumentParser(description="Run the writing agent on a client brief.")
    parser.add_argument(
        "--brief",
        type=str,
        help="Path to a JSON file containing a client brief.",
    )
    parser.add_argument(
        "--client",
        type=str,
        help="Optional client name for session folders (clients/<client>/...).",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="landing",
        choices=["landing", "linkedin", "ux_microcopy", "launch_pack", "audit", "positioning", "ux", "ux_operator", "ux_product"],
        help="Output mode: landing, linkedin, ux_microcopy, launch_pack, audit, positioning, ux, ux_operator, or ux_product (default: landing).",
    )
    args = parser.parse_args()

    client_slug = clean_phrase(args.client) if args.client else None

    brief_path_used: Optional[Path] = None

    if client_slug:
        client_root = Path("clients") / client_slug
        client_root.mkdir(parents=True, exist_ok=True)
        client_brief_path = client_root / "brief.json"

        if args.brief:
            brief = brief_from_file(args.brief)
            brief_path_used = client_brief_path
            with open(client_brief_path, "w", encoding="utf-8") as f:
                json.dump(brief.__dict__, f, indent=2)
        else:
            if client_brief_path.exists():
                brief = brief_from_file(str(client_brief_path))
                brief_path_used = client_brief_path
            else:
                env_brief = brief_from_env()
                if env_brief is not None:
                    brief = env_brief
                else:
                    brief = brief_interactive()
                brief_path_used = client_brief_path
                with open(client_brief_path, "w", encoding="utf-8") as f:
                    json.dump(brief.__dict__, f, indent=2)
    else:
        if args.brief:
            brief = brief_from_file(args.brief)
        else:
            env_brief = brief_from_env()
            if env_brief is not None:
                brief = env_brief
            else:
                brief = brief_interactive()

    return brief, args.mode, client_slug, brief_path_used

