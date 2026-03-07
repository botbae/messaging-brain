"""ProductProfile dataclass — the Messaging Brain for a client.

Stores product-level positioning fields and the extracted decisions dict.
Persists to/from product_profile.json in the client directory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
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
        }

    def save(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
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
        )
