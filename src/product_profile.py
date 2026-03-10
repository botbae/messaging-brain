"""ProductProfile dataclass — the Messaging Brain for a client.

Stores product-level positioning fields and the extracted decisions dict.
Persists to/from product_profile.json in the client directory.

Metadata fields (updated_at, source_idea, client_name) track provenance so
the system can detect when brief.json and product_profile.json refer to
different products under the same client directory.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class ProductProfile:
    product: str = ""
    audience: str = ""
    problem: str = ""
    alternatives: str = ""
    advantage: str = ""
    tone: str = ""
    goal: str = ""
    context: str = ""
    decisions: dict = field(default_factory=dict)
    # Metadata — provenance tracking
    updated_at: str = ""       # ISO 8601 UTC timestamp of last save
    source_idea: str = ""      # the raw idea string that seeded this profile
    client_name: str = ""      # client slug this profile belongs to
    product_fingerprint: str = ""  # sha256 of normalized product+audience+problem

    def _compute_fingerprint(self) -> str:
        """SHA-256 of normalized core identity fields (product + audience + problem)."""
        raw = f"{(self.product or '').strip().lower()}|{(self.audience or '').strip().lower()}|{(self.problem or '').strip().lower()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "product": self.product,
            "audience": self.audience,
            "problem": self.problem,
            "alternatives": self.alternatives,
            "advantage": self.advantage,
            "tone": self.tone,
            "goal": self.goal,
            "context": self.context,
            "decisions": self.decisions,
            "updated_at": self.updated_at,
            "source_idea": self.source_idea,
            "client_name": self.client_name,
            "product_fingerprint": self.product_fingerprint,
        }

    def save(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Always refresh metadata on save
        self.updated_at = datetime.now(timezone.utc).isoformat()
        self.product_fingerprint = self._compute_fingerprint()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path | str) -> "ProductProfile":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls(
            product=data.get("product", ""),
            audience=data.get("audience", ""),
            problem=data.get("problem", ""),
            alternatives=data.get("alternatives", ""),
            advantage=data.get("advantage", ""),
            tone=data.get("tone", ""),
            goal=data.get("goal", ""),
            context=data.get("context", ""),
            decisions=data.get("decisions") or {},
            updated_at=data.get("updated_at", ""),
            source_idea=data.get("source_idea", ""),
            client_name=data.get("client_name", ""),
            product_fingerprint=data.get("product_fingerprint", ""),
        )
