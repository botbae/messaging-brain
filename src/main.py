import argparse
import json
import os
from pathlib import Path
from typing import Optional

from writing_agent import ClientBrief, CriticAgent, WritingAgent


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


def _build_brief_and_mode():
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
        choices=["landing", "linkedin"],
        help="Output mode: landing or linkedin (default: landing).",
    )
    args = parser.parse_args()

    client_slug = _slugify(args.client) if args.client else None

    # Resolve brief depending on client + brief flags
    brief_path_used: Optional[Path] = None

    if client_slug:
        client_root = Path("clients") / client_slug
        client_root.mkdir(parents=True, exist_ok=True)
        client_brief_path = client_root / "brief.json"

        if args.brief:
            # Load from provided path and persist into the client folder.
            brief = _brief_from_file(args.brief)
            brief_path_used = client_brief_path
            with open(client_brief_path, "w", encoding="utf-8") as f:
                json.dump(brief.__dict__, f, indent=2)
        else:
            if client_brief_path.exists():
                # Reuse existing client brief.
                brief = _brief_from_file(str(client_brief_path))
                brief_path_used = client_brief_path
            else:
                # Fall back to hybrid builder (env → interactive), then persist.
                env_brief = _brief_from_env()
                if env_brief is not None:
                    brief = env_brief
                else:
                    brief = _brief_interactive()
                brief_path_used = client_brief_path
                with open(client_brief_path, "w", encoding="utf-8") as f:
                    json.dump(brief.__dict__, f, indent=2)
    else:
        # Existing behavior when no client is specified.
        if args.brief:
            brief = _brief_from_file(args.brief)
        else:
            env_brief = _brief_from_env()
            if env_brief is not None:
                brief = env_brief
            else:
                brief = _brief_interactive()

    return brief, args.mode, client_slug, brief_path_used


def _slugify(text: str) -> str:
    raw = (text or "product").strip().lower()
    if not raw:
        raw = "product"
    chars = []
    for ch in raw:
        if ch.isalnum():
            chars.append(ch)
        else:
            chars.append("-")
    slug = "".join(chars).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "product"


def _next_output_path(product: str, mode: str, client_slug: Optional[str]) -> Path:
    if client_slug:
        base_dir = Path("clients") / client_slug / "outputs"
    else:
        product_slug = _slugify(product)
        base_dir = Path("outputs") / product_slug
    base_dir.mkdir(parents=True, exist_ok=True)

    pattern = f"{mode}_v*.md"
    max_index = 0
    for path in base_dir.glob(pattern):
        stem = path.stem  # e.g. landing_v2
        prefix = f"{mode}_v"
        if not stem.startswith(prefix):
            continue
        suffix = stem[len(prefix) :]
        try:
            idx = int(suffix)
        except ValueError:
            continue
        if idx > max_index:
            max_index = idx

    next_index = max_index + 1 if max_index > 0 else 1
    return base_dir / f"{mode}_v{next_index}.md"


def run() -> str:
    brief, mode, client_slug, brief_path_used = _build_brief_and_mode()
    agent = WritingAgent()

    if mode == "landing":
        draft_v1 = agent.write_landing_page(brief)
        critic = CriticAgent()
        critique = critic.review_landing_page(draft_v1, brief)
        final_text = agent.rewrite_landing_page(brief, draft_v1, critique)
    else:  # linkedin
        final_text = agent.write_linkedin_post(brief)

    out_path = _next_output_path(brief.product, mode, client_slug)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(final_text)

    if brief_path_used is not None:
        print(f"Brief: {brief_path_used}")
    out_path_display = out_path
    print(f"Output: {out_path_display}")

    return final_text


if __name__ == "__main__":
    print(run())
