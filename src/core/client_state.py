"""Client state init and reset — create fresh clients or clear stale state.

Use for:
- Creating a new test client from scratch (no brain, no outputs, no brief).
- Resetting a broken client (clear brain + outputs; optionally invalidate brief).

Does NOT touch other clients. Requires explicit --client name.
"""

from pathlib import Path

from .utils import is_safe_client_slug


def init_client_state(client_slug: str, reset_brief: bool = False) -> dict:
    """Initialize or reset client directory so it has no brain/outputs and optionally no active brief.

    Creates clients/<client_slug>/ if missing. Then:
    - Removes product_profile.json if present (clears brain).
    - Removes idea_extract.json if present.
    - Clears outputs/ (removes all .md files and _manifest.jsonl in that dir).
    - If reset_brief: renames brief.json to brief.json.stale so it cannot leak into generation.

    Returns a small dict with keys: created (bool), brain_removed, idea_extract_removed,
    outputs_cleared, brief_invalidated (if reset_brief).
    """
    if not (client_slug or "").strip():
        return {"error": "client_slug is required"}
    if not is_safe_client_slug(client_slug.strip()):
        return {"error": "client_slug must be letters, digits, '-' or '_' only"}

    client_dir = Path("clients") / client_slug.strip()
    client_dir.mkdir(parents=True, exist_ok=True)
    result = {"created": not any(client_dir.iterdir()) if client_dir.exists() else True}

    # Remove brain
    brain_path = client_dir / "product_profile.json"
    result["brain_removed"] = brain_path.exists()
    if brain_path.exists():
        brain_path.unlink()

    # Remove idea extract
    idea_path = client_dir / "idea_extract.json"
    result["idea_extract_removed"] = idea_path.exists()
    if idea_path.exists():
        idea_path.unlink()

    # Clear outputs
    out_dir = client_dir / "outputs"
    result["outputs_cleared"] = False
    if out_dir.exists():
        for f in out_dir.iterdir():
            if f.is_file():
                f.unlink()
                result["outputs_cleared"] = True
    else:
        out_dir.mkdir(parents=True, exist_ok=True)

    # Optionally invalidate brief so it cannot contaminate next idea/brain
    brief_path = client_dir / "brief.json"
    result["brief_invalidated"] = False
    if reset_brief and brief_path.exists():
        stale_path = brief_path.with_suffix(".json.stale")
        brief_path.rename(stale_path)
        result["brief_invalidated"] = True

    return result
