# Parked Modules

Components that exist or are planned but are not currently active. Documented here so they can be revived later without re-discovery.

---

## 1. Cloud model providers (done)

Anthropic and OpenAI providers are now implemented in `src/core/model_provider.py`. Pick one with `MODEL_PROVIDER=anthropic` or `MODEL_PROVIDER=openai`, or `MODEL_PROVIDER=mixed` for per-agent routing. Kept here only so the numbering below stays stable.

---

## 2. Memory auto-injection

**What it is:** A planned feature where `product_profile.json` decisions would be automatically appended to every LLM prompt at load time — so generators always have the full brain context without explicit injection per mode.

**Current status:** Not implemented. Decision injection is currently done manually, per generator method, in the writers under `src/agents/writing/`.

**Why parked:** Manual injection is more explicit and debuggable. Auto-injection risks silently over-stuffing prompts or causing context conflicts in smaller models. The priority was getting the pipeline working first.

**To activate:** Add a utility function (e.g. `inject_brain_context(system, decisions)`) in `core/model_provider.py` or a new `core/context.py`. Call it in `WritingAgent` methods before each LLM call when `brain_decisions` is set. Consider token budget limits for local models.

---

## 3. CTA consistency checker

**What it is:** A planned validator that would check whether the CTA in generated output is consistent with the `desired_outcome` in the Messaging Brain — catching mismatches like a soft CTA when the brain specifies a direct conversion goal.

**Current status:** Not implemented. The `CriticAgent` does a weak CTA check (flags soft words like "start", "learn", "explore") but does not compare against `desired_outcome`.

**Why parked:** Good-enough validation was in place via `CriticAgent.review_landing_page()`. A semantic CTA/outcome matcher would need either LLM-based comparison or a small keyword/intent map.

**To activate:** Add a `check_cta_alignment(cta: str, desired_outcome: str) -> bool` function in `agents/writing/common.py` or a new `core/validators.py`. Wire it into `CriticAgent.review_landing_page()` and flag `cta_mismatch` in the critique dict.

---

## 4. AGENT_LOOP gaps (ux / ux_product / ux_operator modes)

**What it is:** The `AGENT_LOOP=true` env var enables a critic → strategist → rewrite pipeline for `landing`, `linkedin`, `ux_microcopy`, `launch_pack`, `audit`, and `positioning`. However, `ux`, `ux_product`, and `ux_operator` modes are not wired into the loop — they fall through to direct `agent.write_ux_pack()` calls even when `AGENT_LOOP=true`.

**Current status:** Partially parked. The loop infrastructure exists in `src/agent_loop.py` and could be extended, but no `run_ux_pack_loop()` function exists.

**Why parked:** UX pack output uses a structured validator (`_validate_ux_output`) with strict counts and scenario tags. A critic/strategist loop adds complexity without clear benefit until the UX output quality is well-established.

**To activate:** Add `run_ux_pack_loop(brief, writer, strategist, target)` to `src/agent_loop.py`. Wire it into the `AGENT_LOOP=true` branch in `src/main.py` for `ux`, `ux_product`, and `ux_operator` modes.

---

## 5. write_ux_microcopy() — legacy simple generator

**What it is:** `WritingAgent.write_ux_microcopy()` is a rule-based, no-LLM, no-decisions generator that produces basic onboarding / empty state / error / confirmation copy. It is wired to the `ux_microcopy` mode.

**Current status:** Active in the sense that `--mode ux_microcopy` calls it. But it predates the UX pack system (`write_ux_pack`) and does not use positioning decisions or the Messaging Brain. Output is generic by design.

**Why parked (not deleted):** It is the fallback inside `write_ux_pack()` for the old UX microcopy flow, and `ux_microcopy` mode is still listed as a valid CLI option. Removing it would need a mode deprecation.

**To clean up:** Either deprecate `--mode ux_microcopy` in favor of `--mode ux` / `--mode ux_product`, or rewrite `write_ux_microcopy()` to use decisions like `write_ux_pack()` does. If deprecated, remove from `argparse` choices in `src/core/brief.py` and from the `main.py` dispatch.
