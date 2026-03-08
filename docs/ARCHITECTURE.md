# Backend Architecture

Local prototyping only — no auth, no database, no production infra.

---

## 1. System Overview

The core concept is a three-stage pipeline:

```
idea
  ↓
extract_positioning_decisions
  ↓
product_profile.json  (Messaging Brain)
  ↓
generation modes  (positioning / landing / ux)
  ↓
validators + retry logic
  ↓
versioned outputs
```

A product idea is processed into a set of positioning decisions. Those decisions are stored as the **Messaging Brain** (`product_profile.json`). Every generation call loads the brain first — no repeated LLM extraction, no stale brief values polluting output.

---

## 2. Core Layers

### Input Layer

Three paths into the system — evaluated in priority order:

| Source | How |
|--------|-----|
| `--brief <file>` | JSON file with brief fields |
| Environment variables | `PRODUCT`, `AUDIENCE`, `PAIN`, `OFFER`, `TONE`, `CTA` |
| Interactive prompt | Terminal prompts if no file or env vars |

A **client session** (`--client <name>`) persists the brief to `clients/<name>/brief.json` and loads it on subsequent runs.

Entry: `src/core/brief.py`

---

### Decision Layer

`extract_positioning_decisions()` in `writing_agent.py` takes a `ClientBrief` and returns a decisions dict:

```
icp                — who this is for
primary_problem    — the core pain
desired_outcome    — what the user wants to achieve
category_frame     — what category this product sits in
current_alternative— what users do today instead
differentiation    — what makes this product different
anti_positioning   — what this product is NOT
```

When a `product_profile.json` exists for the client, the decision layer is skipped entirely — the stored brain is used directly. This is the key performance and consistency optimization.

---

### Generation Layer

Three primary generation modes, all driven by brain decisions:

| Mode | Function | Output |
|------|----------|--------|
| `positioning` | `write_positioning()` | 11-section structured positioning doc |
| `landing` | `write_landing_page()` → `rewrite_landing_page()` | Landing page copy with hero, proof, CTA |
| `ux` | `write_ux_pack()` | Onboarding flows, button labels, empty states, toasts |

All generation functions accept the full `ClientBrief` for fallback fact-grounding, but decisions from `brain_decisions` take precedence.

Entry: `src/agents/writing_agent.py`

---

### Validation Layer

Each generation mode has a dedicated validator:

- `_validate_landing_output()` — checks required headers, banned phrases, word counts
- `_validate_ux_output()` — checks section headers, label word count, domain drift
- `_validate_positioning_output()` — checks all 11 positioning headers present, min length

**Banned phrase lists** enforce copy quality:

- `_LANDING_BANNED` — generic marketing phrases banned from landing copy
- `_UX_BANNED` / `_UX_PRODUCT_BANNED` — SaaS workspace vocab banned from UX copy
- `_POSITIONING_BANNED` — generic filler banned from positioning docs
- `_UX_DOMAIN_DRIFT` — domain-specific nouns that signal the LLM has drifted off-topic

**Retry logic** (`_run_with_retry`): on validation failure, the function retries with a stricter prompt variant. After max retries, a rule-based fallback is returned.

---

### Agent Loop

Optional multi-step refinement, enabled via `AGENT_LOOP=true`.

Flow with `AGENT_LOOP`:

```
WritingAgent.generate()
  ↓
CriticAgent.critique()   — flags weak sections
  ↓
StrategistAgent.suggest() — injects positioning/CTA suggestions
  ↓
WritingAgent.rewrite()   — incorporates feedback
```

Without `AGENT_LOOP`, the critic rewrite still runs (single pass) but the strategist is skipped.

Entry: `src/agent_loop.py`

---

### Output System

Each run produces:

- Versioned file: `<mode>_v1.md`, `<mode>_v2.md`, etc.
- Latest symlink: `<mode>_latest.md` (overwritten each run)
- Manifest log: `_manifest.jsonl` (one line per run, append-only)

Output paths:
- Named client: `clients/<client>/outputs/`
- Anonymous: `outputs/<product-slug>/`

Entry: `src/core/output.py`

---

## 3. Messaging Brain

The Messaging Brain is the positioning source of truth for a client. It lives at:

```
clients/<client>/product_profile.json
```

### ProductProfile fields

```python
product       — product name (cleaned, not raw idea text)
audience      — target audience
problem       — primary pain
alternatives  — what users do today instead
advantage     — key differentiator
tone          — voice/tone guidance
goal          — desired user outcome
context       — additional context
decisions     — dict of all extracted positioning decisions (see Decision Layer)
```

### How decisions are stored

`decisions` is a flat dict populated by the LLM during `--mode brain`. Keys match what the generation prompts expect:

```json
{
  "icp": "...",
  "primary_problem": "...",
  "desired_outcome": "...",
  "category_frame": "...",
  "current_alternative": "...",
  "differentiation": "...",
  "anti_positioning": "..."
}
```

### How generation uses the brain

In `main.py` and `api/app.py`:

1. `_load_profile_if_exists(client_slug)` — loads `product_profile.json` if present
2. `_resolve_brief_from_profile(brief, profile)` — returns a new `ClientBrief` where profile fields override stale brief fields (cta, examples, context are kept from brief)
3. The resolved brief + `profile.decisions` are passed to `WritingAgent`
4. `WritingAgent.brain_decisions` is set — `extract_positioning_decisions()` returns it immediately, skipping LLM extraction

This means generation is deterministic and fast when a brain exists.

---

## 4. Generation Modes

### positioning

Generates an 11-section structured positioning document.

Sections: PRODUCT | ICP | CORE PROBLEM | CURRENT ALTERNATIVE | WHY CURRENT OPTIONS FAIL | DESIRED OUTCOME | CATEGORY FRAME | DIFFERENTIATION | ANTI-POSITIONING | POSITIONING STATEMENT | MESSAGING NOTES

CLI: `python src/main.py --mode positioning --client <name>`
API: `POST /generate/positioning`

---

### landing

Generates landing page copy. Sections: HEADLINE | SUBHEAD | WHO IT'S FOR | PROOF | CTA.

Rules enforced:
- Headline ≤ 12 words
- Subhead ≤ 25 words
- No time claims ("in minutes", "under an hour")
- No generic CTAs ("Sign up today")

After draft generation, a senior-editor LLM pass tightens the copy before returning.

CLI: `python src/main.py --mode landing --client <name>`
API: `POST /generate/landing`

---

### ux

Generates a UX copy pack: onboarding flows, button labels, empty states, toast messages, error messages.

Rules enforced:
- Toast ≤ 8 words
- Empty state ≤ 12 words
- Button labels 1–4 words, domain-specific
- No SaaS workspace vocabulary (campaign, workflow, pipeline, ticket, insight, stage)

CLI: `python src/main.py --mode ux --client <name>`
API: `POST /generate/ux`

---

## 5. API Layer

Thin FastAPI wrapper over the CLI backend. Same functions, exposed over HTTP.

Start the server from the repo root:

```bash
PYTHONPATH=src uvicorn src.api.app:app --reload --port 8000
```

Interactive docs: `http://localhost:8000/docs`

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/idea` | Extract ICP, problem, category, differentiation from a free-text idea |
| POST | `/brain` | Run full positioning LLM pass from a brief; save brain |
| POST | `/brain/save` | Persist edited brain fields back to `product_profile.json` |
| POST | `/generate/positioning` | Generate positioning doc from stored brain |
| POST | `/generate/landing` | Generate landing page from stored brain |
| POST | `/generate/ux` | Generate UX pack from stored brain |

Full request/response examples: see `docs/API.md`.

---

## 6. Storage Model

All client state lives under `clients/`:

```
clients/
  <client>/
    brief.json              — raw client brief (CLI args or API payload)
    product_profile.json    — Messaging Brain (positioning decisions)
    idea_extract.json       — output of --mode idea (quick extraction)
    outputs/
      positioning_v1.md
      positioning_latest.md
      landing_v1.md
      landing_latest.md
      ux_v1.md
      ux_latest.md
      _manifest.jsonl       — append-only run log
```

Anonymous runs (no `--client`) write to `outputs/<product-slug>/`.

`outputs/` and `clients/*/outputs/` are gitignored.

---

## 7. Model Layer

The LLM backend is selected via the `MODEL_PROVIDER` environment variable.

```
MODEL_PROVIDER=ollama   (default) — local Ollama at localhost:11434, model llama3:8b
MODEL_PROVIDER=cloud    — stub; raises NotImplementedError
```

All generation code imports `generate` from `core.model_provider`, not `core.llm` directly.

### Adding a cloud provider

Implement `CloudProviderStub.generate()` in `src/core/model_provider.py`:

```python
class CloudProviderStub:
    def generate(self, prompt: str, system: str = "", temperature: float = 0.7) -> str:
        # Replace with actual API call (Anthropic, OpenAI, etc.)
        raise NotImplementedError
```

Then set `MODEL_PROVIDER=cloud` at runtime. No other files need to change.

---

## 8. Message Engine Flow (full)

```
                    ┌─────────────┐
                    │  User input │
                    │ (idea/brief)│
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  core/brief │  load brief (file > env > interactive)
                    └──────┬──────┘
                           │
              ┌────────────▼────────────┐
              │  product_profile.json   │  brain exists?
              │   (Messaging Brain)     │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │ extract_positioning_    │  brain absent → LLM extraction
              │ decisions()             │  brain present → return stored
              └────────────┬────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
  ┌──────▼──────┐  ┌───────▼──────┐  ┌──────▼──────┐
  │ positioning │  │   landing    │  │     ux       │
  │ write_      │  │ write_       │  │ write_       │
  │ positioning │  │ landing_page │  │ ux_pack      │
  └──────┬──────┘  └───────┬──────┘  └──────┬──────┘
         │                 │                 │
         └─────────────────┼─────────────────┘
                           │
              ┌────────────▼────────────┐
              │  validators + banned    │  fail → retry with strict prompt
              │  phrase checks          │  max retries → rule-based fallback
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  versioned output       │  <mode>_vN.md + <mode>_latest.md
              │  + manifest log         │  + _manifest.jsonl entry
              └─────────────────────────┘
```
