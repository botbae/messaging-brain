"""GroundingAgent: checks extracted decisions still match the brief.

Split out of agents/writing_agent.py; import from there for a stable API.
"""

import re

from dataclasses import dataclass

from core.utils import clean_phrase, clean_sentence
from agents.writing.common import ClientBrief


@dataclass
class GroundingAgent:
    """Verifies that LLM-extracted decisions are semantically grounded in the source brief.

    Uses token-level Jaccard overlap (stdlib only). If a decision field has no token
    overlap with its corresponding brief field, it is patched back to the brief value.
    """

    name: str = "GroundingAgent"
    threshold: float = 0.05  # minimum Jaccard overlap before patching

    def _jaccard(self, a: str, b: str) -> float:
        ta = set(re.sub(r"[^\w\s]", "", (a or "").lower()).split())
        tb = set(re.sub(r"[^\w\s]", "", (b or "").lower()).split())
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / len(ta | tb)

    def ground(self, decisions: dict, brief: ClientBrief) -> tuple[dict, list[str]]:
        """Patch decisions that have drifted from brief fields. Returns (patched, notes)."""
        patched = dict(decisions)
        notes: list[str] = []

        icp = patched.get("icp", "")
        if self._jaccard(icp, brief.audience or "") < self.threshold:
            patched["icp"] = clean_phrase(brief.audience) or icp
            notes.append("icp: low overlap with brief.audience — patched")

        problem = patched.get("primary_problem", "")
        if self._jaccard(problem, brief.pain or "") < self.threshold:
            patched["primary_problem"] = clean_sentence(brief.pain or problem)
            notes.append("primary_problem: low overlap with brief.pain — patched")

        return patched, notes
