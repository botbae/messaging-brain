# Unimind Backend

A messaging intelligence engine that takes a product idea, extracts positioning decisions, and generates structured copy outputs: positioning documents, landing pages, and UX copy.

**Local prototyping only — no auth, no database, no production infra.**

---

## What it does

1. **Idea extraction** — parse a free-text product idea into ICP, problem, category, differentiation
2. **Messaging Brain** — run a full positioning LLM pass from a brief; store decisions as `product_profile.json`
3. **Positioning** — generate an 11-section structured positioning document
4. **Landing page** — generate validated landing copy (headline, subhead, proof, CTA)
5. **UX copy** — generate onboarding flows, button labels, empty states, toasts

All generation is driven by the Messaging Brain. Once a brain exists for a client, generation is fast and deterministic — no repeated LLM extraction.

---

## Prerequisites

- Python 3.12+, venv active
- [Ollama](https://ollama.com) running locally with `llama3:8b`

```bash
ollama pull llama3:8b
```

---

## Quick start

All commands run from the repo root.

```bash
# 1. Extract positioning from an idea
python src/main.py --mode idea --idea "An AI tool that writes landing pages for B2B SaaS founders" --client myproduct

# 2. Run full brain from a brief
python src/main.py --mode brain --brief clients/myproduct/brief.json --client myproduct

# 3. Generate outputs
python src/main.py --mode positioning --client myproduct
python src/main.py --mode landing --client myproduct
python src/main.py --mode ux --client myproduct
```

### API server

```bash
PYTHONPATH=src uvicorn src.api.app:app --reload --port 8001
```

Interactive docs: `http://localhost:8001/docs`

### Frontend

The frontend is a separate repository. Point it at `http://localhost:8001` and ensure the backend is running before starting it.

---

## CLI reference

```bash
# All available modes
python src/main.py --mode <mode> --client <name>
# modes: idea | brain | positioning | landing | ux | linkedin | ux_microcopy | launch_pack | audit | ux_operator | ux_product | init_client

# Initialize a fresh client for testing (removes brain, idea_extract, clears outputs)
# python src/main.py --client test-unimind-clean --mode init_client
# Full reset including brief: python src/main.py --client test-unimind-clean --mode init_client --reset-brief

# From a brief file
python src/main.py --brief briefs/sample.json --mode landing

# Debug: print positioning decisions before generation
DEBUG_DECISIONS=true python src/main.py --client myproduct --mode landing

# Enable multi-step critic/strategist loop
AGENT_LOOP=true python src/main.py --client myproduct --mode landing

# Open output in default app after generation (macOS)
OPEN_LATEST=true python src/main.py --client myproduct --mode landing
```

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/idea` | Extract positioning from a free-text idea |
| POST | `/brain` | Run full positioning LLM pass and save brain |
| POST | `/brain/save` | Persist edited brain fields to `product_profile.json` |
| POST | `/client/init` | Initialize or reset a client directory |
| POST | `/generate/landing` | Generate landing page from stored brain |
| POST | `/generate/ux` | Generate UX pack from stored brain |
| POST | `/generate/positioning` | Generate positioning doc from stored brain |
| GET | `/readiness/{client}/{mode}` | Check whether client has enough data to generate |

### Request/response examples

```bash
# Extract from idea
curl -X POST http://localhost:8001/idea \
  -H "Content-Type: application/json" \
  -d '{"idea": "An AI tool that writes landing pages for B2B SaaS founders", "client": "myproduct"}'

# Run brain from brief
curl -X POST http://localhost:8001/brain \
  -H "Content-Type: application/json" \
  -d '{
    "client": "myproduct",
    "brief": {
      "product": "MyProduct",
      "audience": "B2B SaaS founders",
      "pain": "Cannot explain their product clearly to buyers",
      "offer": "AI-generated landing pages and UX copy",
      "tone": "clear, confident, and human",
      "cta": "Start your free brief"
    }
  }'

# Save edited brain fields
curl -X POST http://localhost:8001/brain/save \
  -H "Content-Type: application/json" \
  -d '{
    "client": "myproduct",
    "idea_extract": {
      "icp": "B2B SaaS founders",
      "problem": "Cannot explain their product clearly to buyers",
      "category": "AI writing tools",
      "differentiation": "Writes from your positioning, not a blank prompt"
    }
  }'

# Initialize a fresh client (clear brain, idea extract, outputs)
curl -X POST http://localhost:8001/client/init \
  -H "Content-Type: application/json" \
  -d '{"client": "myproduct", "reset_brief": false}'

# Generate landing page
curl -X POST http://localhost:8001/generate/landing \
  -H "Content-Type: application/json" \
  -d '{"client": "myproduct"}'

# Generate UX pack
curl -X POST http://localhost:8001/generate/ux \
  -H "Content-Type: application/json" \
  -d '{"client": "myproduct"}'

# Generate positioning doc
curl -X POST http://localhost:8001/generate/positioning \
  -H "Content-Type: application/json" \
  -d '{"client": "myproduct"}'
```

Full API documentation: `docs/API.md`

---

## Where outputs are saved

```
clients/myproduct/
  brief.json                     — raw brief
  product_profile.json           — Messaging Brain (positioning decisions)
  idea_extract.json              — idea extraction output
  outputs/
    positioning_v1.md
    positioning_latest.md
    landing_v1.md
    landing_latest.md
    ux_v1.md
    ux_latest.md
    _manifest.jsonl              — append-only run log
```

`outputs/` and `clients/*/outputs/` are gitignored.

---

## Repository structure

```
src/
  main.py                  — CLI entry point; orchestrates brief loading, brain, dispatch, output saving
  agent_loop.py            — Multi-step critic/strategist loop (AGENT_LOOP=true)
  product_profile.py       — ProductProfile dataclass (the Messaging Brain)
  agents/
    writing_agent.py       — All agents and generators: WritingAgent, CriticAgent, StrategistAgent
  core/
    brief.py               — Brief loading (file > env > interactive); --client session logic
    llm.py                 — Raw Ollama HTTP client (stdlib urllib) — do not import directly
    model_provider.py      — Provider abstraction: OllamaProvider, CloudProviderStub, get_provider()
    output.py              — Output path versioning and manifest logging
    utils.py               — Text helpers: clean_sentence, clean_phrase, lower_first
  api/
    app.py                 — FastAPI wrapper; exposes idea/brain/generate endpoints over HTTP

clients/                   — Per-client briefs, brains, and outputs (outputs/ gitignored)
memory/                    — System Brain: engineering rules, decisions, evolution log, failure notes
docs/                      — Architecture, API reference, prompts, walkthroughs, parked modules
briefs/                    — Sample brief JSON files
```

### Key directories

| Directory | Purpose |
|-----------|---------|
| `src/agents/` | All LLM generation and validation logic |
| `src/core/` | Infrastructure: LLM client, brief loading, output, utilities |
| `src/api/` | HTTP API layer (FastAPI) |
| `clients/` | Per-client persistent state (brief + brain + outputs) |
| `memory/` | Engineering context: rules, decisions, failure notes |
| `docs/` | Documentation: architecture, API, prompts, walkthroughs |

---

## Architecture summary

```
idea / brief
     ↓
core/brief.py  (load input)
     ↓
product_profile.json  (Messaging Brain — source of truth)
     ↓
extract_positioning_decisions()  (skipped if brain exists)
     ↓
write_positioning() / write_landing_page() / write_ux_pack()
     ↓
validators + banned phrase checks  (retry on failure)
     ↓
versioned output files
```

Full architecture documentation: `docs/ARCHITECTURE.md`

---

## Backend status

This repository implements the core messaging intelligence engine for Unimind.

**MVP complete:**

- Idea extraction (ICP, problem, category, differentiation)
- Messaging Brain (positioning decisions stored per client)
- Positioning document generation (11-section structured output)
- Landing page generation (validated copy with quality enforcement)
- UX copy generation (onboarding, labels, empty states, toasts)
- Validation and retry logic (banned phrases, word counts, domain drift detection)
- API interface (FastAPI, 8 endpoints)

**Not yet implemented (future phases):**

- Tests — no test suite; generators and validators are untested in isolation
- Auth / session management — no authentication, no multi-user separation
- Persistent storage — all state is file-based; no database
- Cloud model providers — `CloudProviderStub` is a hook, not an implementation
- Formal schemas — `ClientBrief` and `ProductProfile` are dataclasses, not Pydantic models

Frontend, authentication, storage scaling, and cloud model providers will be implemented in future phases. The frontend should live in a separate repo and call this backend over HTTP.
