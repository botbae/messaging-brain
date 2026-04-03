"""ProductProfile dataclass — the Messaging Brain for a client.

Stores product-level positioning fields and the extracted decisions dict.
Persists to/from product_profile.json in the client directory.

Metadata fields (updated_at, source_idea, client_name) track provenance so
the system can detect when brief.json and product_profile.json refer to
different products under the same client directory.

DecisionDict
------------
``decisions`` is a ``DecisionDict`` — a dict subclass where:
- Values are always plain strings when accessed via ``get()`` / ``[]``.  All
  existing callers (``decisions.get("icp", "")``) are unaffected.
- Each entry *optionally* carries ``confidence`` (float) and ``source_notes``
  (str) metadata stored in a parallel ``_meta`` dict that does NOT affect
  normal dict iteration or ``dict()`` copies.
- ``get_entry(key)`` → ``{"value": str, "confidence": float, "source_notes": str}``
- ``set_entry(key, value, confidence, source_notes)`` → stores both.
- ``to_serializable()`` → plain dict for JSON; entries that have meta are
  serialized as ``{"value": ..., "confidence": ..., "source_notes": ...}``.

On load, ``_load_decisions()`` normalizes:
- plain strings  → stored as-is (no meta)
- rich dicts (have "value" key) → string extracted, meta restored
- arbitrary dicts / None / other → string-coerced, confidence 0.5
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# DecisionDict — backward-compatible decisions container with rich metadata
# ---------------------------------------------------------------------------

class DecisionDict(dict):
    """A decisions dict that transparently stores plain string values while
    optionally carrying per-entry metadata (confidence, source_notes).

    Design invariant: the underlying ``dict`` always holds plain ``str``
    values so that ``dict(some_decision_dict)`` (used in generation_context.py)
    produces a normal ``{key: str}`` copy without any loss or surprise.
    Rich metadata lives in ``self._meta`` and is never part of dict storage.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Parallel metadata keyed the same as the main dict.
        # Not a dict field — invisible to dict() copies and iteration.
        self._meta: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Rich-entry API
    # ------------------------------------------------------------------

    def get_entry(self, key: str) -> Optional[dict]:
        """Return ``{"value", "confidence", "source_notes"}`` or None if key is absent."""
        if key not in self:
            return None
        meta = self._meta.get(key, {})
        return {
            "value": self[key],
            "confidence": meta.get("confidence", 1.0),
            "source_notes": meta.get("source_notes", ""),
        }

    def set_entry(
        self,
        key: str,
        value: str,
        confidence: float = 1.0,
        source_notes: str = "",
    ) -> None:
        """Store a rich decision entry (string value + metadata)."""
        self[key] = value
        self._meta[key] = {"confidence": float(confidence), "source_notes": str(source_notes)}

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_serializable(self) -> dict:
        """Return a plain dict suitable for ``json.dump``.

        Entries that have metadata are written as
        ``{"value": str, "confidence": float, "source_notes": str}`` so the
        information survives a save/load round-trip.  Entries without metadata
        are written as plain strings (backward-compatible).
        """
        out: dict = {}
        for key, val in self.items():
            meta = self._meta.get(key)
            if meta:
                out[key] = {
                    "value": val,
                    "confidence": meta.get("confidence", 1.0),
                    "source_notes": meta.get("source_notes", ""),
                }
            else:
                out[key] = val
        return out


def _load_decisions(raw: dict) -> DecisionDict:
    """Normalize a raw JSON decisions dict into a ``DecisionDict``.

    Handles three legacy shapes:
    - plain string  → stored as-is (confidence defaults to 1.0, no notes)
    - rich dict with "value" key → string extracted, meta restored
    - arbitrary dict without "value" / None / other → coerced to string,
      confidence set to 0.5 to signal the value was guessed
    """
    d = DecisionDict()
    for key, val in raw.items():
        if isinstance(val, str):
            d[key] = val
        elif isinstance(val, dict) and "value" in val:
            d.set_entry(
                key,
                str(val.get("value") or ""),
                float(val.get("confidence") or 1.0),
                str(val.get("source_notes") or ""),
            )
        elif val is None:
            d[key] = ""
        else:
            # Arbitrary dict without a "value" key or unexpected type — best-effort
            d.set_entry(key, str(val), 0.5, "normalized from unknown format")
    return d


# ---------------------------------------------------------------------------
# ProductProfile
# ---------------------------------------------------------------------------

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
    decisions: DecisionDict = field(default_factory=DecisionDict)
    # Metadata — provenance tracking
    updated_at: str = ""           # ISO 8601 UTC; kept for backward compat — mirrors last_saved_at
    source_idea: str = ""          # the raw idea string that seeded this profile
    client_name: str = ""          # client slug this profile belongs to
    product_fingerprint: str = ""  # sha256 of normalized product+audience+problem
    # Versioning — added for lightweight persistent memory
    brain_version: int = 0         # incremented on every save; 0 on profiles that predate this field
    last_saved_at: str = ""        # ISO 8601 UTC timestamp of the most recent save

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
            "decisions": self.decisions.to_serializable() if isinstance(self.decisions, DecisionDict) else self.decisions,
            "updated_at": self.updated_at,
            "source_idea": self.source_idea,
            "client_name": self.client_name,
            "product_fingerprint": self.product_fingerprint,
            "brain_version": self.brain_version,
            "last_saved_at": self.last_saved_at,
        }

    def save(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Refresh all metadata fields atomically from the same instant.
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        self.updated_at = now_iso          # legacy field — kept for backward compat
        self.last_saved_at = now_iso       # canonical versioning timestamp
        self.brain_version += 1
        self.product_fingerprint = self._compute_fingerprint()
        data = self.to_dict()
        # Write main profile
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        # Write timestamped snapshot to brain_history/<timestamp>_v<n>.json
        snapshot_dir = path.parent / "brain_history"
        snapshot_dir.mkdir(exist_ok=True)
        snapshot_name = now.strftime("%Y%m%dT%H%M%SZ") + f"_v{self.brain_version}.json"
        with open(snapshot_dir / snapshot_name, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

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
            decisions=_load_decisions(data.get("decisions") or {}),
            updated_at=data.get("updated_at", ""),
            source_idea=data.get("source_idea", ""),
            client_name=data.get("client_name", ""),
            product_fingerprint=data.get("product_fingerprint", ""),
            brain_version=data.get("brain_version", 0),
            last_saved_at=data.get("last_saved_at", ""),
        )


# ---------------------------------------------------------------------------
# Brain suggestions — lightweight rule-based quality guidance (V1)
# ---------------------------------------------------------------------------

# Phrases that signal a field value is generic/placeholder and should be
# treated as effectively empty.
_GENERIC_FRAGMENTS: tuple[str, ...] = (
    "your product",
    "your audience",
    "your customers",
    "target audience",
    "potential customers",
    "various users",
    "everyone",
    "anyone who",
    "all users",
    "all businesses",
    "small businesses",
    "companies that",
    "people who want",
    "users who need",
    "those who",
)

# Words that suggest a problem statement describes a feature rather than pain.
_FEATURE_WORDS: tuple[str, ...] = (
    "feature",
    "functionality",
    "tool",
    "solution",
    "platform",
    "system",
    "software",
    "dashboard",
    "integration",
    "api",
    "module",
    "interface",
)

# Words that indicate a short problem statement still expresses real pain or
# consequence — used to suppress the "vague" suggestion when the statement is
# brief but clearly meaningful.
_PAIN_WORDS: tuple[str, ...] = (
    "lose",
    "waste",
    "miss",
    "delay",
    "confuse",
    "error",
    "errors",
    "manual",
    "slow",
    "costly",
    "expensive",
    "churn",
    "blocked",
    "fail",
    "failing",
    "stockout",
    "overstock",
)

# Role nouns that indicate an audience value, even if short or partially
# generic, refers to a concrete buyer type rather than "everyone".
_ROLE_NOUNS: tuple[str, ...] = (
    "founder",
    "founders",
    "owner",
    "owners",
    "operator",
    "operators",
    "marketer",
    "marketers",
    "designer",
    "designers",
    "developer",
    "developers",
    "pm",
    "pms",
    "manager",
    "managers",
    "team",
    "teams",
)

# Words suggesting an advantage/differentiation overlaps too much with
# the problem (i.e. the field just restates the problem as the win).
_ADVANTAGE_OVERLAP_WORDS: tuple[str, ...] = (
    "lack",
    "missing",
    "don't have",
    "do not have",
    "without",
    "no way to",
    "struggle",
    "manual",
    "slow",
    "hard to",
    "difficult to",
)


# Lighter domain → alternative examples map used when generating contextual
# ai_suggestion values for empty alternatives fields.
_ALT_EXAMPLES: dict[str, str] = {
    "ecommerce":   "spreadsheets, CRM tools, email flows, agencies",
    "retention":   "email tools, manual CRM, spreadsheets",
    "inventory":   "spreadsheets, ERP systems, dashboards",
    "messaging":   "ChatGPT prompts, copywriters, Notion docs",
    "positioning": "ChatGPT prompts, copywriters, Notion docs",
    "copywriting": "freelance writers, ChatGPT, Notion templates",
    "landing":     "Webflow templates, ChatGPT, agencies",
    "analytics":   "spreadsheets, BI tools, dashboards, Looker",
    "reporting":   "spreadsheets, manual reports, dashboards",
    "finance":     "spreadsheets, CFO consultants, QuickBooks",
    "recruiting":  "LinkedIn, ATS tools, spreadsheets",
    "hiring":      "LinkedIn, job boards, spreadsheets",
    "sales":       "CRM manual setup, spreadsheets, email follow-ups",
    "crm":         "spreadsheets, Notion, manual email",
    "marketing":   "ChatGPT prompts, agencies, spreadsheets",
    "content":     "freelance writers, ChatGPT, agencies",
    "social":      "manual posting, scheduling tools, agencies",
    "ux":          "user interviews, Notion docs, UX agencies",
    "operations":  "spreadsheets, Notion, email chains",
    "scheduling":  "email chains, spreadsheets, back-and-forth",
    "support":     "email manually, Intercom manual, spreadsheets",
    "influencer":  "DM manually, spreadsheets, agencies",
    "creator":     "manual outreach, spreadsheets, brand decks",
    "developer":   "CLI scripts, documentation, manual processes",
    "saas":        "spreadsheets, manual onboarding, email chains",
}


def _contextual_suggestion(field: str, profile: "ProductProfile") -> str:
    """Return a concrete, context-specific suggested value for a weak field.

    Uses available profile data (category, audience, product) to produce
    a specific example rather than repeating generic writing advice.
    Returns "" when no useful inference is possible.
    """
    audience = (profile.audience or profile.decisions.get("icp") or "").strip()
    problem = (profile.problem or profile.decisions.get("primary_problem") or "").strip()
    category = (profile.decisions.get("category_frame") or "").strip()
    advantage = (profile.advantage or profile.decisions.get("differentiation") or "").strip()
    product = (profile.product or "").strip()

    # Last noun of audience (e.g. "early-stage SaaS founders" → "founders")
    audience_noun = audience.split(",")[0].split()[-1] if audience else ""

    if field == "alternatives":
        combined = (category + " " + product).lower()
        for kw, alts in _ALT_EXAMPLES.items():
            if kw in combined:
                return alts
        return "spreadsheets, manual workflows, agencies, or existing tools in this space"

    elif field == "problem":
        return ""

    elif field == "goal":
        if audience_noun and product:
            prod_short = product[:40]
            return f"{audience_noun} get a working {prod_short[:25]} without manual guesswork"
        return ""

    elif field == "advantage":
        if category and audience_noun:
            cat_word = category.split()[0] if category.split() else "this"
            return (
                f"Built specifically for {audience_noun}, unlike general-purpose "
                f"{cat_word} tools that require heavy setup"
            )
        if problem:
            prob_short = problem[:40]
            return f"Directly solves \"{prob_short}\" instead of leaving it to the user"
        return ""

    elif field == "audience":
        if category:
            cat_word = category.split()[0].capitalize() if category.split() else "this"
            return f"seed-stage B2B founders using {cat_word}"
        return ""

    return ""


def _is_blank(value: str) -> bool:
    return not value or not value.strip()


def _is_generic(value: str) -> bool:
    v = value.lower()
    return any(frag in v for frag in _GENERIC_FRAGMENTS)


def _word_count(value: str) -> int:
    return len(value.split()) if value else 0


def suggest_brain_improvements(profile: "ProductProfile") -> list[dict]:
    """Return a list of structured improvement suggestions for the Messaging Brain.

    Each suggestion has:
      field    — the profile field name the suggestion targets
      severity — "warning" (missing/high-risk) or "info" (useful improvement)
      message  — short, actionable text for display

    Rules are purely deterministic; no LLM calls are made.
    Low-confidence metadata (confidence < 0.7) escalates info → warning.
    """
    suggestions: list[dict] = []

    def _add(field: str, severity: str, message: str) -> None:
        entry: dict = {"field": field, "severity": severity, "message": message}
        ai_sug = _contextual_suggestion(field, profile)
        if ai_sug:
            entry["ai_suggestion"] = ai_sug
        suggestions.append(entry)

    def _confidence(decisions_key: str) -> float:
        entry = profile.decisions.get_entry(decisions_key)
        return entry["confidence"] if entry else 1.0

    def _escalate(base_severity: str, decisions_key: str) -> str:
        """Upgrade info → warning when confidence on the mapped decision is low."""
        if base_severity == "info" and _confidence(decisions_key) < 0.7:
            return "warning"
        return base_severity

    # --- audience ---
    audience = (profile.audience or profile.decisions.get("icp") or "").strip()
    if _is_blank(audience):
        _add("audience", "warning", "Audience is missing. Add a specific buyer, role, or team.")
    elif _is_generic(audience) or _word_count(audience) <= 3:
        a_lower = audience.lower()
        has_role = any(rn in a_lower.split() for rn in _ROLE_NOUNS)
        if has_role:
            # Broad but includes a concrete role noun — soften to info unless
            # low-confidence escalation applies.
            _add("audience", _escalate("info", "icp"),
                 "Audience is broad. Narrow it to a specific buyer, role, or team.")
        else:
            # No concrete role noun — keep the stronger current behaviour.
            sev = "warning" if _word_count(audience) <= 2 or _is_blank(audience) else _escalate("info", "icp")
            _add("audience", sev,
                 "Audience is broad. Narrow it to a specific buyer, role, or team.")

    # --- problem ---
    problem = (profile.problem or profile.decisions.get("primary_problem") or "").strip()
    if _is_blank(problem):
        _add("problem", "warning", "Problem is missing. Describe the real pain your product solves.")
    else:
        p_lower = problem.lower()
        detected_fw = next((fw for fw in _FEATURE_WORDS if fw in p_lower), None)
        if detected_fw:
            _add("problem", _escalate("info", "primary_problem"),
                 f"Problem mentions '{detected_fw}' — that's a feature, not a pain. "
                 "Describe the consequence it causes for your users instead.")
        elif _word_count(problem) <= 5 and not any(pw in p_lower for pw in _PAIN_WORDS):
            # Short and no pain/consequence signal — flag as vague.
            _add("problem", _escalate("info", "primary_problem"),
                 f"Problem is only {_word_count(problem)} words and lacks a consequence. "
                 "Add what breaks, slows down, or costs money when this isn't solved.")

    # --- alternatives ---
    alternatives = (profile.alternatives or profile.decisions.get("current_alternative") or "").strip()
    if _is_blank(alternatives):
        # Build a domain hint from category if available
        _cat = (profile.decisions.get("category_frame") or profile.product or "").lower()
        _domain_hint = ""
        for kw, alts in _ALT_EXAMPLES.items():
            if kw in _cat:
                _domain_hint = f" For this space, likely candidates: {alts}."
                break
        _add("alternatives", "warning",
             f"Alternatives is empty — the landing page can't explain why existing options fall short.{_domain_hint}")

    # --- advantage ---
    advantage = (profile.advantage or profile.decisions.get("differentiation") or "").strip()
    product_words = set((profile.product or "").lower().split())
    if _is_blank(advantage):
        _add("advantage", "warning",
             "Advantage is empty. Describe what makes this product different from the alternatives.")
    else:
        a_lower = advantage.lower()
        # Check if advantage overlaps with problem words (just restates the pain)
        problem_words = set(problem.lower().split()) if problem else set()
        adv_words = set(a_lower.split())
        overlap = adv_words & problem_words - {"the", "a", "an", "and", "or", "of", "to", "in", "is", "it"}
        if any(w in a_lower for w in _ADVANTAGE_OVERLAP_WORDS):
            _add("advantage", _escalate("info", "differentiation"),
                 "Advantage may overlap with the problem. Focus on the structural reason why this product wins.")
        elif len(overlap) >= 4:
            _add("advantage", "info",
                 "Advantage shares many words with the problem field. Make sure it describes the win, not just the pain.")

    # --- tone ---
    tone = (profile.tone or profile.decisions.get("tone") or "").strip()
    if _is_blank(tone):
        _add("tone", "info",
             "Tone is empty. Add a tone descriptor (e.g. 'direct', 'confident', 'empathetic') to guide copy style.")

    # --- goal ---
    goal = (profile.goal or profile.decisions.get("desired_outcome") or "").strip()
    if _is_blank(goal):
        _add("goal", "warning",
             "Goal is missing. Add the outcome the user achieves after using the product.")
    elif _word_count(goal) <= 3:
        _add("goal", _escalate("info", "desired_outcome"),
             f"Goal is only {_word_count(goal)} words. Describe the specific outcome: "
             "what changes for the user after using this product?")

    return suggestions


# ---------------------------------------------------------------------------
# Brain strength scoring — lightweight quality evaluation for frontend display
# ---------------------------------------------------------------------------

def score_brain_strength(profile: "ProductProfile") -> dict:
    """Score the Messaging Brain's quality for frontend display.

    Returns:
        {
            "score": float (0.0–1.0),
            "label": "weak" | "moderate" | "strong",
            "field_scores": {field: {"score": float, "note": str}, ...},
        }

    Scoring is deterministic — no LLM calls.
    """

    def _field_score(value: str, min_good_words: int = 4) -> tuple[float, str]:
        """Score a single field: 0.0 (missing), 0.5 (generic/short), 1.0 (specific)."""
        v = (value or "").strip()
        if not v:
            return 0.0, "missing"
        wc = len(v.split())
        v_lower = v.lower()
        # Check for generic filler
        if any(frag in v_lower for frag in _GENERIC_FRAGMENTS):
            return 0.3, "generic"
        if wc < min_good_words:
            return 0.5, "too short"
        return 1.0, "good"

    decisions = profile.decisions or {}

    fields = {
        "product": (profile.product or "", 2),
        "audience": (decisions.get("icp") or profile.audience or "", 3),
        "problem": (decisions.get("primary_problem") or profile.problem or "", 4),
        "alternatives": (decisions.get("current_alternative") or profile.alternatives or "", 3),
        "advantage": (decisions.get("differentiation") or profile.advantage or "", 4),
        "goal": (decisions.get("desired_outcome") or profile.goal or "", 3),
    }

    field_scores = {}
    total = 0.0
    for name, (value, min_words) in fields.items():
        score, note = _field_score(value, min_words)
        field_scores[name] = {"score": score, "note": note}
        total += score

    avg = total / len(fields) if fields else 0.0

    if avg >= 0.8:
        label = "strong"
    elif avg >= 0.5:
        label = "moderate"
    else:
        label = "weak"

    return {
        "score": round(avg, 2),
        "label": label,
        "field_scores": field_scores,
    }
