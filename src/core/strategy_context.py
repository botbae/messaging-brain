"""Strategy context layers: Positioning and Narrative.

Sits between GenerationContext (merged brain + brief + overrides) and
the output generators.  Generators consume these two objects instead of
raw brief fields — this ensures consistent, product-grounded output.

Architecture:
    GenerationContext
        → PositioningContext   (what this product IS)
        → NarrativeContext     (the STORY around it)
        → output generators
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from core.utils import clean_phrase, clean_sentence


# ---------------------------------------------------------------------------
# PositioningContext
# ---------------------------------------------------------------------------

@dataclass
class PositioningContext:
    """Strategic positioning decisions that define what the product IS.

    Every field is a short, concrete string — not marketing copy.
    """
    category: str = ""          # What kind of product this is
    enemy: str = ""             # The current alternative / what users do today
    icp: str = ""               # Ideal customer profile
    core_problem: str = ""      # The real friction users face
    differentiation: str = ""   # Why this product, not the alternative
    anti_positioning: str = ""  # What this product is NOT
    promise: str = ""           # The one-line desired outcome

    def filled_count(self) -> int:
        """Number of non-empty fields."""
        return sum(1 for f in (self.category, self.enemy, self.icp,
                               self.core_problem, self.differentiation,
                               self.anti_positioning, self.promise) if f.strip())

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "enemy": self.enemy,
            "icp": self.icp,
            "core_problem": self.core_problem,
            "differentiation": self.differentiation,
            "anti_positioning": self.anti_positioning,
            "promise": self.promise,
        }


# ---------------------------------------------------------------------------
# NarrativeContext
# ---------------------------------------------------------------------------

@dataclass
class NarrativeContext:
    """Product narrative — the STORY that grounds all generated copy.

    Each field is 1-3 sentences synthesized from positioning + brief.
    These are NOT user-facing copy — they are internal context that
    generators translate into section-specific output.
    """
    product_story: str = ""       # What the product is and why it exists
    user_journey: str = ""        # What the user's path looks like
    transformation: str = ""      # Before → after: the change the product enables
    problem_story: str = ""       # The user's lived experience of the problem
    solution_story: str = ""      # How the product solves it, mechanically

    def filled_count(self) -> int:
        return sum(1 for f in (self.product_story, self.user_journey,
                               self.transformation, self.problem_story,
                               self.solution_story) if f.strip())

    def to_dict(self) -> dict:
        return {
            "product_story": self.product_story,
            "user_journey": self.user_journey,
            "transformation": self.transformation,
            "problem_story": self.problem_story,
            "solution_story": self.solution_story,
        }


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------

@dataclass
class NarrativeReadiness:
    ready: bool
    positioning_filled: int = 0
    narrative_filled: int = 0
    message: str = ""


def assess_narrative_readiness(pos: PositioningContext, nar: NarrativeContext,
                                mode: str) -> NarrativeReadiness:
    """Check whether positioning + narrative are rich enough for a given mode."""
    # Minimum positioning fields for each mode
    _MIN_POS = {"landing": 4, "ux": 4, "ux_product": 4, "linkedin": 3,
                "positioning": 5, "launch_pack": 3}
    # Minimum narrative fields for each mode
    _MIN_NAR = {"landing": 3, "ux": 3, "ux_product": 3, "linkedin": 2,
                "positioning": 2, "launch_pack": 2}

    pf = pos.filled_count()
    nf = nar.filled_count()
    min_p = _MIN_POS.get(mode, 2)
    min_n = _MIN_NAR.get(mode, 1)

    if pf < min_p or nf < min_n:
        parts = []
        if pf < min_p:
            parts.append(f"positioning has {pf}/{min_p} fields")
        if nf < min_n:
            parts.append(f"narrative has {nf}/{min_n} fields")
        msg = (
            f"Not enough context for high-quality {mode} output ({', '.join(parts)}). "
            "Run --mode brain with a fuller brief to enrich the messaging brain."
        )
        return NarrativeReadiness(ready=False, positioning_filled=pf,
                                   narrative_filled=nf, message=msg)

    return NarrativeReadiness(ready=True, positioning_filled=pf,
                               narrative_filled=nf, message="")


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def build_positioning_context(gen_ctx) -> PositioningContext:
    """Derive PositioningContext from a GenerationContext.

    Maps brain decision keys → positioning fields with sensible fallbacks.
    """
    d = gen_ctx.decisions or {}

    category = d.get("category_frame") or ""
    enemy = d.get("current_alternative") or ""
    icp = d.get("icp") or gen_ctx.audience or ""
    core_problem = d.get("primary_problem") or gen_ctx.pain or ""
    differentiation = d.get("differentiation") or ""
    anti_positioning = d.get("anti_positioning") or ""
    promise = d.get("desired_outcome") or gen_ctx.offer or ""

    return PositioningContext(
        category=category,
        enemy=enemy,
        icp=icp,
        core_problem=core_problem,
        differentiation=differentiation,
        anti_positioning=anti_positioning,
        promise=promise,
    )


def _synthesize_field(parts: list[str], joiner: str = " ") -> str:
    """Join non-empty parts into a single string."""
    return joiner.join(p.strip() for p in parts if p and p.strip())


def build_narrative_context(gen_ctx, pos: PositioningContext) -> NarrativeContext:
    """Derive NarrativeContext from GenerationContext + PositioningContext.

    Synthesizes short narrative strings from positioning decisions and brief
    fields.  These are internal context — not user-facing copy.
    """
    product = clean_phrase(gen_ctx.product) or "This product"
    icp_lower = pos.icp.lower().rstrip(".") if pos.icp else "users"

    # Product story: what it is and why it exists
    product_story = ""
    if pos.category and pos.core_problem:
        product_story = (
            f"{product} is a {pos.category.lower().rstrip('.')} "
            f"built because {icp_lower} face a real problem: "
            f"{pos.core_problem.rstrip('.')}"
        )
    elif pos.category:
        product_story = f"{product} is a {pos.category.lower().rstrip('.')} for {icp_lower}."
    elif gen_ctx.pain:
        product_story = f"{product} exists because {icp_lower} struggle with {gen_ctx.pain.lower().rstrip('.')}."
    else:
        product_story = f"{product} for {icp_lower}."

    # User journey: what the user's path looks like
    user_journey = ""
    if pos.core_problem and pos.promise:
        user_journey = (
            f"{icp_lower.capitalize()} start with {pos.core_problem.lower().rstrip('.')}. "
            f"Through {product}, they reach {pos.promise.lower().rstrip('.')}."
        )
    elif pos.core_problem:
        user_journey = (
            f"{icp_lower.capitalize()} come in with {pos.core_problem.lower().rstrip('.')} "
            f"and work through {product} to get clarity."
        )

    # Transformation: before → after
    transformation = ""
    if pos.core_problem and pos.promise:
        transformation = (
            f"Before: {pos.core_problem.rstrip('.')}. "
            f"After: {pos.promise.rstrip('.')}."
        )
    elif pos.promise:
        transformation = f"After using {product}: {pos.promise.rstrip('.')}."

    # Problem story: the user's lived experience
    problem_story = ""
    if pos.core_problem and pos.enemy:
        problem_story = (
            f"{pos.core_problem.rstrip('.')}. "
            f"Today, {icp_lower} use {pos.enemy.lower().rstrip('.')} "
            f"but it does not solve the real issue."
        )
    elif pos.core_problem:
        problem_story = pos.core_problem
    elif gen_ctx.pain:
        problem_story = gen_ctx.pain

    # Solution story: how the product solves it
    solution_story = ""
    if pos.differentiation and pos.category:
        solution_story = (
            f"{product} works as a {pos.category.lower().rstrip('.')}. "
            f"{pos.differentiation.rstrip('.')}."
        )
    elif pos.differentiation:
        solution_story = f"{product}: {pos.differentiation.rstrip('.')}."
    elif gen_ctx.offer:
        solution_story = f"{product} delivers {gen_ctx.offer.lower().rstrip('.')}."

    return NarrativeContext(
        product_story=product_story,
        user_journey=user_journey,
        transformation=transformation,
        problem_story=problem_story,
        solution_story=solution_story,
    )


# ---------------------------------------------------------------------------
# Convenience: build both in one call
# ---------------------------------------------------------------------------

def build_strategy_layers(gen_ctx) -> tuple[PositioningContext, NarrativeContext]:
    """Build both strategy layers from a GenerationContext."""
    pos = build_positioning_context(gen_ctx)
    nar = build_narrative_context(gen_ctx, pos)
    return pos, nar


# ---------------------------------------------------------------------------
# Debug logging
# ---------------------------------------------------------------------------

def log_strategy_context(pos: PositioningContext, nar: NarrativeContext) -> None:
    """Print strategy context to stdout for pipeline visibility."""
    if os.getenv("DEBUG_STRATEGY", "").lower() != "true":
        return
    print("\n--- POSITIONING CONTEXT ---")
    for k, v in pos.to_dict().items():
        print(f"  {k}: {v}")
    print("--- NARRATIVE CONTEXT ---")
    for k, v in nar.to_dict().items():
        print(f"  {k}: {v}")
    print("--- END STRATEGY ---\n")
