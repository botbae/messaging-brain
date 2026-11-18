"""Safe folder paths for client data.

Every client gets a folder under clients/. Client names come from users (CLI flag
or API request), so they are checked here before they ever touch the filesystem:
the name must be a plain folder name, and the final resolved path must still sit
inside clients/.
"""

import os
from pathlib import Path

from .utils import is_safe_client_slug

CLIENTS_DIR = "clients"


class UnsafeClientName(ValueError):
    """Raised when a client name could point outside the clients/ folder."""


def client_dir(client_slug: str) -> Path:
    """Return clients/<client_slug> as a path, or raise UnsafeClientName."""
    slug = (client_slug or "").strip()
    if not is_safe_client_slug(slug):
        raise UnsafeClientName(
            f"Invalid client name {client_slug!r}: use letters, digits, '-' or '_' only."
        )
    base = os.path.realpath(CLIENTS_DIR)
    full = os.path.realpath(os.path.join(base, slug))
    if not full.startswith(base + os.sep):
        raise UnsafeClientName(f"Invalid client name {client_slug!r}: path escapes clients/.")
    return Path(os.path.relpath(full))
