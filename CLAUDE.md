# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the agent

All commands run from the repo root with the venv active. The entry point is `src/main.py` and must be run from the repo root so relative imports resolve.

```bash
# Interactive (prompts for brief fields)
python src/main.py

# From a JSON brief file
python src/main.py --brief briefs/sample.json --mode landing

# With a named client session (persists brief to clients/<name>/brief.json)
python src/main.py --brief clients/unimind/brief.json --client unimind --mode linkedin

# All available modes
# landing | linkedin | ux_microcopy | launch_pack | audit | positioning | ux | ux_operator | ux_product | brain | idea | init_client

# Initialize a fresh client (removes brain + idea_extract + clears outputs; use for clean testing)
# python src/main.py --client test-unimind-clean --mode init_client
# Optionally invalidate stale brief: python src/main.py --client test-unimind-clean --mode init_client --reset-brief

# Via environment variables
PRODUCT="..." AUDIENCE="..." PAIN="..." OFFER="..." TONE="..." CTA="..." python src/main.py

# Enable multi-step critic/strategist loop
AGENT_LOOP=true python src/main.py --brief briefs/sample.json

# Open output in default app after generation (macOS)
OPEN_LATEST=true python src/main.py --brief briefs/sample.json

# Show strategy block appended to output
SHOW_STRATEGY=true AGENT_LOOP=true python src/main.py --brief briefs/sample.json

# Debug: print positioning decisions extracted from brain before generation
DEBUG_DECISIONS=true python src/main.py --client unimind --mode landing
```

The LLM backend is **Ollama running locally** (`http://localhost:11434`) with `llama3:8b`. Ollama must be running before invoking the agent.

## Architecture

```
src/main.py              — Entry point; orchestrates brief loading, brain loading, agent dispatch, output saving
src/agent_loop.py        — Multi-step loop functions (run_landing_loop, run_linkedin_loop, etc.)
src/core/brief.py        — Brief loading: --brief file > env vars > interactive prompts; --client session logic
src/core/llm.py          — Ollama HTTP client (stdlib urllib, no SDK) — do not call directly
src/core/model_provider.py — Minimal provider abstraction: OllamaProvider, CloudProviderStub, get_provider()
src/core/output.py       — Output path versioning (clients/<slug>/outputs/<mode>_vN.md or outputs/<slug>/...)
src/core/utils.py        — Text helpers: clean_sentence, clean_phrase, lower_first
src/agents/writing_agent.py — All agents: WritingAgent (with brain_decisions field), CriticAgent, StrategistAgent, ClientBrief
src/product_profile.py   — ProductProfile dataclass: the Messaging Brain; load/save product_profile.json
```

## Execution flow: idea → brain → generate

```
idea      --mode idea --idea "..." [--client <name>]
              LLM extracts {icp, problem, category, differentiation}
              If --client: saves idea_extract.json + seeds product_profile.json (brain)

brain     --mode brain --brief <path> --client <name>
              Loads full brief, runs positioning LLM, saves complete product_profile.json

generate  --mode landing|linkedin|ux|positioning ... --client <name>
              Loads product_profile.json → agent.brain_decisions (skips re-extraction LLM call)
              Brief provides raw context for fallbacks and fact-grounding only
```

**Flow without AGENT_LOOP:**
`main.py` → `core/brief.py` (load brief) → load brain if exists → `agents/writing_agent.py` (generate draft, optionally critic rewrite) → save versioned output

**Flow with AGENT_LOOP=true:**
Same, but `agent_loop.py` adds a `StrategistAgent` step between critic and rewrite, injecting positioning/CTA suggestions.

## Model provider

`core/model_provider.py` selects the LLM backend via `MODEL_PROVIDER` env var (default: `ollama`).
- `MODEL_PROVIDER=ollama` — local Ollama at `localhost:11434` (current default)
- `MODEL_PROVIDER=cloud` — stub (raises NotImplementedError; implement `CloudProviderStub.generate()` to add cloud support)

All code should import `generate` from `core.model_provider`, not `core.llm` directly.

## Brief and output conventions

- `ClientBrief` fields: `product`, `audience`, `pain`, `offer`, `tone`, `cta`, `examples`, `context`
- Named client sessions store their brief at `clients/<client>/brief.json` and outputs at `clients/<client>/outputs/`
- Anonymous runs write to `outputs/<product-slug>/`
- Each run writes a versioned file (`<mode>_vN.md`) and overwrites `<mode>_latest.md`
- A `_manifest.jsonl` log is appended per run in the output directory

## Memory layers

Two memory layers exist (both currently file-based):

**Product Brain** — per-client messaging intelligence, lives in `clients/<client>/`:
- `product_profile.json` — extracted positioning decisions (the Messaging Brain, source of truth)
- `brief.json` — raw client brief
- `idea_extract.json` — output of `--mode idea`
- `outputs/` — all generated artifacts

**System Brain** — engineering context about Unimind itself, lives in `memory/` and `docs/`:
- `memory/system_rules.md` — rules for content generation (landing, LinkedIn, UX) and source-of-truth conventions
- `memory/evolution/` — one markdown file per architectural milestone
- `memory/failures/` — bugs and prompt failures worth remembering to avoid repeating
- `memory/decisions/` — architectural choices with tradeoffs documented
- `memory/modules/` — module state notes (active, parked, removed)
- `docs/` — PROMPTS.md, WALKTHROUGH.md, parked_modules.md
- See `memory/README.md` for the full System Brain index and write rules

## Future direction

The backend is a local CLI ready for **frontend prototyping**. It is **not production-hardened yet**.

Before treating it as a production backend, the following are missing:
- **Tests** — no test suite exists; generators and validators are untested in isolation
- **API layer** — FastAPI wrapper exists at `src/api/app.py` (6 endpoints); not production-hardened (no auth, no rate limiting)
- **Formal schemas** — `ClientBrief` and `ProductProfile` are dataclasses, not validated schemas (no Pydantic, no JSON Schema enforcement at boundaries)
- **Auth / state model** — no authentication, no session management, no multi-user separation
- **Robust error surfaces** — LLM failures currently fall back to rule-based templates silently; a real API needs structured error responses

For prototyping, the backend can be wrapped in a thin HTTP layer that calls the same functions `main.py` already calls:

```
POST /idea        — extract ICP, problem, category, differentiation from a product idea string
POST /brain       — run full positioning LLM from a brief, save product_profile.json
POST /generate/landing
POST /generate/linkedin
POST /generate/ux
```

If a frontend is built, it should live in a separate repo and call this backend. Do not add web framework code to this repo without first splitting it into an API layer.

## Notes

- `docs/experimental/hello.py` is a standalone Anthropic SDK smoke test (requires `ANTHROPIC_API_KEY` in `.env`), not part of the main workflow
- `outputs/` and `clients/*/outputs/` are gitignored
- See `docs/parked_modules.md` for components that are planned but not yet active
