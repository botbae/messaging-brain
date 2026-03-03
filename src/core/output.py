"""Output paths and versioning for generated files."""

from pathlib import Path

from .utils import clean_phrase


def slugify(text: str) -> str:
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


def next_output_path(product: str, mode: str, client_slug: str | None) -> Path:
    if client_slug:
        base_dir = Path("clients") / clean_phrase(client_slug) / "outputs"
    else:
        product_slug = slugify(product)
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

