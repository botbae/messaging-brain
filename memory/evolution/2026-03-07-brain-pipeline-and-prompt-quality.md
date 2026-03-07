# Evolution: Brain pipeline stable + prompt quality pass

**Date:** 2026-03-07

## Milestone

The idea → brain → generate pipeline is end-to-end working and parked in a clean state.

## What was built

### Messaging Brain pipeline
- `--mode idea` — LLM extracts `{icp, problem, category, differentiation}` from a raw idea string; seeds `product_profile.json`
- `--mode brain` — loads a full brief, runs the positioning LLM, saves complete `product_profile.json` with all 7 decisions
- All generation modes (`landing`, `linkedin`, `ux`, etc.) load `product_profile.json` at startup; `agent.brain_decisions` is set and the decision-extraction LLM call is skipped

### Source of truth
`clients/<client>/product_profile.json` is the Messaging Brain. It contains:
- Brief-derived fields: `product`, `audience`, `problem`, `alternatives`, `advantage`, `tone`, `goal`, `context`
- Extracted decisions: `icp`, `primary_problem`, `current_alternative`, `desired_outcome`, `category_frame`, `differentiation`, `anti_positioning`

### Provider abstraction
`src/core/model_provider.py` provides `OllamaProvider` (active) and `CloudProviderStub` (parked — raises NotImplementedError). Configured via `MODEL_PROVIDER` env var.

### Prompt quality improvements
Two prompt-level fixes applied in this session:

1. **Landing page** — system and user prompts now include per-section directives:
   - HEADLINE must name ICP and desired_outcome in a declarative statement
   - PROBLEM must state primary_problem in plain language
   - WHY CURRENT OPTIONS FAIL must name the specific gap in current_alternative
   - DIFFERENTIATION must contrast with anti_positioning
   - PROOF / SIGNALS must provide a concrete signal, not "To be added"

2. **UX pack (product mode)** — critical fix: `decisions` dict was loaded from brain but never injected into the LLM prompt. ICP, primary_problem, desired_outcome, and differentiation are now explicitly passed into both system and user prompts, making the Messaging Brain the driver of UX microcopy rather than the brief fields alone.

## What is parked

See `docs/parked_modules.md` for full details on:
- CloudProviderStub (hook exists, implementation missing)
- Memory auto-injection (planned, not implemented)
- CTA consistency checker (planned, not implemented)
- AGENT_LOOP gaps for ux/ux_product/ux_operator modes
- write_ux_microcopy() legacy simple generator

---

## AI_CONTEXT

```yaml
component: full pipeline
system_stage: v2 — brain pipeline stable, prompt quality improved
notes:
  - product_profile.json is source of truth for all generators
  - brain_decisions field on WritingAgent bypasses re-extraction LLM call
  - per-section prompt instructions added to write_landing_page()
  - decisions now injected into write_ux_pack() product mode (was a bug — they were loaded but not passed)
  - CloudProviderStub exists but raises NotImplementedError
  - repo is clean enough to pause and resume
```
