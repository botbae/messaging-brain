# UX pack product mode: brain decisions loaded but never injected into prompt

**Date:** 2026-03-07
**Affected:** `src/agents/writing_agent.py` — `WritingAgent.write_ux_pack()`

## What happened

When `--mode ux` or `--mode ux_product` ran with a client that had a `product_profile.json`, the Messaging Brain decisions were loaded correctly by `_load_brain_if_exists()` and set on `agent.brain_decisions`. However, the `write_ux_pack()` method called `extract_positioning_decisions()` to get those decisions, then **never passed them into the LLM prompt**. The user prompt for product mode was built from `brief.*` fields only. Generated UX microcopy reflected the raw brief rather than the brain.

## Root cause

In `write_ux_pack()`, the `else` branch (product mode) built `user_parts` using `brief.product`, `brief.audience`, `brief.pain`, `brief.offer`, and `brief.tone` — but not the `decisions` dict that had just been returned from `extract_positioning_decisions()`. The decisions variable existed in scope but was never referenced when constructing the prompt.

The same variable was also never passed into the `system` string or `system_strict` string for product mode.

## Fix

Extracted `icp`, `primary_problem`, `desired_outcome`, and `differentiation` from the decisions dict at the top of the `else` branch and injected them explicitly into both the `user_parts` list and the `system` string. The `system_strict` fallback was also updated to include `icp_strict` and `problem_strict`.

## Watch for

Any generator method that calls `extract_positioning_decisions()` but then builds its prompt from `brief.*` fields directly — the decisions may be silently ignored. When adding a new mode or editing a generator, confirm that the decisions dict fields (`icp`, `primary_problem`, `desired_outcome`, `category_frame`, `differentiation`, `anti_positioning`) appear in the actual prompt strings, not just the brief fields.
