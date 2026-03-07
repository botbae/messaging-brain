# Walkthrough: Decisions, generation, validation, outputs

## Folder structure map

| Path | Purpose |
|------|--------|
| `src/main.py` | Orchestrator: parses CLI, loads brief and brain, runs the right mode, saves versioned + latest output, appends to manifest. |
| `src/agents/` | Brains: `writing_agent.py` (WritingAgent, CriticAgent, StrategistAgent, FactGuardAgent, GroundingAgent). Decision extractor and all content generators live here. |
| `src/core/` | Plumbing: `brief.py` (load brief from file/env/interactive), `output.py` (versioned paths), `llm.py` (Ollama API), `model_provider.py` (provider abstraction), `utils.py` (text helpers). |
| `src/agent_loop.py` | Loops that run critic/strategist + rewrite for landing, LinkedIn, and other modes (when `AGENT_LOOP=true`). |
| `src/product_profile.py` | ProductProfile dataclass: load/save `product_profile.json` (the Messaging Brain). |
| `clients/<client>/brief.json` | Memory of the client brief (saved when using `--client` and file or interactive input). |
| `clients/<client>/product_profile.json` | The Messaging Brain for this client: extracted positioning decisions. Source of truth for all generators. |
| `clients/<client>/idea_extract.json` | Raw output of `--mode idea` if `--client` was used. |
| `clients/<client>/outputs/` | Generated artifacts for that client: versioned `*_vN.md`, `*_latest.md`, and `_manifest.jsonl`. |
| `outputs/<product-slug>/` | Same structure when no `--client` is used (e.g. `--brief briefs/sample.json`). |
| `memory/` | System Brain: `system_rules.md`, `evolution/` log entries, `README.md`. |
| `docs/` | Human and AI-readable documentation: PROMPTS.md, WALKTHROUGH.md, parked_modules.md. |

---

## Execution flow: idea → brain → generate

The pipeline has three stages. Each stage builds on the previous one.

### Stage 1: idea

```
python src/main.py --mode idea --idea "..." [--client <name>]
```

- LLM extracts `{icp, problem, category, differentiation}` from the idea string.
- If `--client` is provided:
  - Saves raw extract to `clients/<client>/idea_extract.json`
  - Seeds `clients/<client>/product_profile.json` (Messaging Brain — partial)
- Run `--mode brain` next with a full brief to complete the brain.

### Stage 2: brain

```
python src/main.py --mode brain --brief <path> --client <name>
```

- Loads the full brief.
- Runs the positioning LLM (`extract_positioning_decisions`) to produce 7 decisions:
  `icp`, `primary_problem`, `current_alternative`, `desired_outcome`, `category_frame`, `differentiation`, `anti_positioning`
- Saves complete `clients/<client>/product_profile.json`.
- This file is the **source of truth** for all downstream generation.

### Stage 3: generate

```
python src/main.py --client <name> --mode landing
python src/main.py --client <name> --mode ux
python src/main.py --client <name> --mode linkedin
# etc.
```

- `main.py` calls `_load_brain_if_exists(client_slug)` → loads `decisions` from `product_profile.json`.
- Sets `agent.brain_decisions = decisions` → no re-extraction LLM call is made.
- Generator (e.g. `write_landing_page`) uses the preloaded decisions as the single source of truth.
- Brief provides raw context only for fallbacks and fact-grounding.

---

## Decision phase

1. `WritingAgent.extract_positioning_decisions()` builds the strategy layer from brief fields — or returns `brain_decisions` immediately if they were preloaded.
2. It expects strict JSON with 7 keys:
   `icp`, `primary_problem`, `current_alternative`, `desired_outcome`, `category_frame`, `differentiation`, `anti_positioning`.
3. If JSON is invalid or contains banned language, it retries with a stricter prompt.
4. If retry fails, it uses deterministic fallback decisions derived from the brief.
5. `GroundingAgent` checks Jaccard overlap between extracted decisions and brief fields — patches drifted decisions back to the brief source.

## Expression phase

1. Content modes (`landing`, `linkedin`, `ux`) use extracted decisions plus tone instructions.
2. Prompts include per-section instructions mapping each decision to the correct output section.
3. Banned phrase lists prevent generic SaaS language from leaking in.
4. Optional `AGENT_LOOP=true` mode adds critic/strategist refinement passes (landing, linkedin, positioning, ux_microcopy, launch_pack, audit).

## Validation phase

1. Generated text is checked for required headers and banned phrases per mode.
2. If validation fails, generation retries once with stricter instructions.
3. If still invalid or Ollama unavailable, deterministic fallback templates are returned.
4. `FactGuardAgent` strips numeric claims not grounded in brief.examples or brief.context.

## Where to find latest outputs

1. Run any mode, for example:
   `python src/main.py --client unimind --mode landing`
2. CLI prints both saved paths:
   - Versioned output path (`*_vN.md`)
   - Latest output path (`*_latest.md`)
3. Open the latest files directly:
   - `clients/unimind/outputs/landing_latest.md`
   - `clients/unimind/outputs/ux_latest.md`
   - `clients/unimind/outputs/linkedin_latest.md`
   - `clients/unimind/outputs/positioning_latest.md`
4. `_manifest.jsonl` in the same folder appends one JSON line per run.
