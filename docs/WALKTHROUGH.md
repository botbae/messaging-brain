# Walkthrough: Decisions, generation, validation, outputs

## Folder structure map

| Path | Purpose |
|------|--------|
| `src/main.py` | Orchestrator: parses CLI, loads brief, runs the right mode, saves versioned + latest output, appends to manifest. |
| `src/agents/` | Brains: `writing_agent.py` (WritingAgent, CriticAgent, StrategistAgent). Decisions extractor and all content generators live here. |
| `src/core/` | Plumbing: `brief.py` (load brief from file/env/interactive), `output.py` (versioned paths), `llm.py` (Ollama API), `utils.py` (text helpers). |
| `src/agent_loop.py` | Loops that run critic/strategist + rewrite for landing, LinkedIn, etc. |
| `clients/<client>/brief.json` | Memory of the client brief (saved when using `--client` and file or interactive input). |
| `clients/<client>/outputs/` | Generated artifacts for that client: versioned `*_vN.md`, `*_latest.md`, and `_manifest.jsonl`. |
| `outputs/<product-slug>/` | Same structure when no `--client` is used (e.g. `--brief briefs/sample.json`). |

## Decision phase

1. `WritingAgent.extract_positioning_decisions()` builds the strategy layer from brief fields.
2. It expects strict JSON with 7 keys:
`icp`, `primary_problem`, `current_alternative`, `desired_outcome`, `category_frame`, `differentiation`, `anti_positioning`.
3. If JSON is invalid or contains banned language, it retries with a stricter prompt.
4. If retry fails, it uses deterministic fallback decisions from the brief.

## Expression phase

1. Content modes (`landing`, `linkedin`, `ux`) use extracted decisions plus tone instructions.
2. Prompts enforce exact output structure and explicit banned phrase lists.
3. Optional `AGENT_LOOP=true` mode adds critic/strategist refinement passes.

## Validation phase

1. Generated text is checked for required headers and banned phrases per mode.
2. If validation fails, generation retries once with stricter instructions.
3. If still invalid/unavailable, deterministic fallback templates are returned.

## Where to find latest outputs

1. Run any mode, for example:
`python src/main.py --client demo --mode linkedin`
2. CLI prints both saved paths:
- Versioned output path (`*_vN.md`)
- Latest output path (`*_latest.md`)
3. Open the latest files directly:
- `clients/demo/outputs/linkedin_latest.md`
- `clients/demo/outputs/landing_latest.md`
- `clients/demo/outputs/ux_latest.md`
- `clients/demo/outputs/positioning_latest.md`
4. `_manifest.jsonl` in the same folder appends one JSON line per run.
