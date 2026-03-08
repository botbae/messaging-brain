"""Brief loading: file/env/interactive and client sessions."""

import argparse
import json
import os
from pathlib import Path
from typing import Optional, Tuple

from agents.writing_agent import ClientBrief
from .utils import clean_phrase


def _brief_from_profile_path(profile_path: Path) -> Optional[ClientBrief]:
    """Construct a ClientBrief from a saved product_profile.json. Returns None on failure."""
    try:
        from product_profile import ProductProfile
        profile = ProductProfile.load(profile_path)
        d = profile.decisions or {}
        return ClientBrief(
            product=profile.product or "",
            audience=d.get("icp") or profile.audience or "",
            pain=d.get("primary_problem") or profile.problem or "",
            offer=d.get("desired_outcome") or d.get("differentiation") or profile.advantage or "",
            tone=profile.tone or "",
            cta="",
            examples="",
            context=profile.context or "",
        )
    except Exception:
        return None


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
        product=data.get("product", "") or "",
        audience=data.get("audience", "") or "",
        pain=data.get("pain", "") or "",
        offer=data.get("offer", "") or "",
        tone=data.get("tone", "") or "",
        cta=data.get("cta", "") or "",
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
        product=product or "",
        audience=audience or "",
        pain=pain or "",
        offer=offer or "",
        tone=tone or "",
        cta=cta or "",
        examples=examples or "",
        context=context or "",
    )


def brief_interactive() -> ClientBrief:
    default_product = os.getenv("PRODUCT", "")

    product = prompt("Product", default_product)
    audience = prompt("Audience", "")
    pain = prompt("Main pain you solve", "")
    offer = prompt("Primary offer", "")
    tone = prompt("Tone", "clear and direct")
    cta = prompt("Primary call-to-action", "")
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


def build_brief_and_mode() -> Tuple[ClientBrief, str, Optional[str], Optional[Path], Optional[str]]:
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
        choices=["landing", "linkedin", "ux_microcopy", "launch_pack", "audit", "positioning", "ux", "ux_operator", "ux_product", "brain", "idea"],
        help="Output mode: landing, linkedin, ux_microcopy, launch_pack, audit, positioning, ux, ux_operator, ux_product, brain, or idea (default: landing).",
    )
    parser.add_argument(
        "--idea",
        type=str,
        default=None,
        help="Product idea string (for --mode idea).",
    )
    args = parser.parse_args()

    client_slug = clean_phrase(args.client) if args.client else None
    idea_text = getattr(args, "idea", None) or None

    # Idea mode: only need --idea; no brief file or interactive prompt.
    # client_slug is passed through so main.py can save the extract and seed the brain.
    if args.mode == "idea" and idea_text:
        from agents.writing_agent import ClientBrief
        idea_client_slug = clean_phrase(args.client) if args.client else None
        minimal_brief = ClientBrief(
            product=idea_text.strip(),
            audience="",
            pain="",
            offer="",
            tone="",
            cta="",
            examples="",
            context="",
        )
        return minimal_brief, "idea", idea_client_slug, None, idea_text.strip()

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
                # No brief.json yet — check for a saved product profile before prompting.
                # After /idea or /brain, product_profile.json exists but brief.json may not.
                # Constructing the brief from the profile avoids stale interactive defaults.
                profile_path = client_root / "product_profile.json"
                profile_brief = _brief_from_profile_path(profile_path) if profile_path.exists() else None
                if profile_brief is not None:
                    brief = profile_brief
                    print(f"Brief resolved from existing product profile: {profile_path}")
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

    return brief, args.mode, client_slug, brief_path_used, idea_text

