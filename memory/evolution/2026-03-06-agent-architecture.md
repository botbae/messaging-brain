# Evolution: Agent architecture stabilization

**Date:** 2026-03-06

## Problem

AI outputs were inconsistent and leaked operator language (e.g. brief.json, CLI commands, generation modes) into product-facing UX copy.

## Solution

Introduced structured validators, a decision extraction layer, and explicit UX pack rules so outputs stay aligned with the brief and never reference operator workflows in product mode.

## Key Components

- **extract_positioning_decisions()** — Pulls ICP, primary_problem, current_alternative, desired_outcome, category_frame, differentiation, anti_positioning from the brief (LLM + fallback).
- **UX validators** — Enforce headers, counts (3,3,3,3,8), banned phrases, scenario tags `[brief intake]`, `[decision review]`, `[generation review]` for product mode; operator terms forbidden in product UX.
- **ProductProfile brain layer** — Thin product layer: ProductProfile dataclass, `--mode brain` (save decisions to product_profile.json), `--mode idea` (one-shot idea extraction).
- **CLI modes:** landing, linkedin, ux_product, brain, idea (and existing positioning, ux_operator, ux_microcopy, launch_pack, audit).

## Example Before

Generic outputs and operator leaks (e.g. "Generate landing", "brief.json", "Output saved") in product UX copy.

## Example After

Decision-driven outputs aligned with the brief; product UX speaks only to end-users (brief intake, decision review, generation review) with no CLI or file-path references.

---

## AI_CONTEXT

```yaml
component: writing_agent
system_stage: v1 architecture stabilization
notes:
  - validators enforce structure
  - outputs grounded in brief decisions
```
