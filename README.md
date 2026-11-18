# Messaging Brain

Turn a rough product idea into a **Messaging Brain**: a small, saved set of positioning decisions (who it's for, the problem, the alternative, the differentiation). Then generate copy from it: landing page blueprints, positioning docs, LinkedIn posts and UX microcopy, all grounded in the same decisions.

It's a Python CLI plus a small FastAPI server. It runs fully local and free with [Ollama](https://ollama.com), or with Anthropic or OpenAI if you add a key.

> Status: working prototype, built as a portfolio project. Good for local use, experiments and forking. Not production hardened (no auth, no rate limits).

## How it works

```
idea  ──►  Messaging Brain  ──►  landing · positioning · LinkedIn · UX copy
           (product_profile.json)        each checked by validators, with retry
```

1. **Idea**: an LLM pulls the audience, problem, category and differentiation out of a free-text idea.
2. **Brain**: a full brief becomes 7 positioning decisions, saved to `clients/<name>/product_profile.json` with a confidence score.
3. **Generate**: every writer reads the brain instead of re-asking the model, so outputs stay consistent.

Every output is checked for required sections and banned hype phrases ("revolutionize", "seamless", ...). If the model's answer fails twice, or no model is running, a rule-based template is used instead, so you always get something usable.

## Quick start (5 minutes)

Needs Python 3.11 or newer.

```bash
git clone https://github.com/botbae/messaging-brain.git
cd messaging-brain
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # optional: pick a model provider or add keys
```

**Pick a model** (in `.env`):

| `MODEL_PROVIDER` | What you need |
|---|---|
| `ollama` (default) | Install Ollama, then `ollama pull llama3:8b` and keep it running |
| `anthropic` | `ANTHROPIC_API_KEY` |
| `openai` | `OPENAI_API_KEY` |

No model at all? It still runs, using the template fallback. Output is plainer, but it's a good way to try it.

**Run it:**

```bash
# One-off landing page blueprint from a sample brief
python src/main.py --brief briefs/sample.json --mode landing

# Full flow for a named client: idea -> brain -> outputs
python src/main.py --mode idea --idea "A reminder app for dentists" --client acme
python src/main.py --mode brain --brief briefs/sample.json --client acme
python src/main.py --mode positioning --client acme
python src/main.py --mode linkedin --client acme
```

Outputs land in `outputs/<product>/` or `clients/<name>/outputs/` as versioned Markdown (`landing_v1.md`, `landing_latest.md`).

Modes: `idea`, `brain`, `landing`, `positioning`, `linkedin`, `ux`, `ux_product`, `ux_operator`, `ux_microcopy`, `launch_pack`, `audit`, `init_client`.

Handy switches: `AGENT_LOOP=true` adds a critic and strategist rewrite pass, `DEBUG_DECISIONS=true` prints the brain before generating.

### API server

```bash
uvicorn src.api.app:app --reload --port 8000
```

Open http://localhost:8000/docs for interactive docs. Main endpoints: `POST /idea`, `POST /brain`, `POST /brain/save`, `POST /generate/{mode}`, `GET /client/{name}/confidence`. Full examples in [docs/API.md](docs/API.md).

The server has no login. Keep it on your own machine.

## Project layout

```
src/
  main.py                CLI entry point
  api/app.py             FastAPI server
  agents/
    writing_agent.py     WritingAgent: one entry point for every output
    writing/             one file per output: landing, positioning, linkedin, ux, launch_pack
    critic_agent.py      scores drafts and suggests fixes (AGENT_LOOP)
    strategist_agent.py  positioning and CTA suggestions (AGENT_LOOP)
    extraction_agent.py  idea -> decisions
  core/                  model providers, brief loading, confidence scoring, output paths
  product_profile.py     the Messaging Brain data model
  schemas/               Pydantic models for structured outputs
tests/                   offline test suite (no model needed)
docs/                    architecture, API, prompts, walkthrough
memory/                  dev journal: decisions, failures and lessons from building it
briefs/                  sample briefs to try
```

More detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/WALKTHROUGH.md](docs/WALKTHROUGH.md).

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests switch the model off, so they're fast, free and run the same everywhere. GitHub Actions runs them on every push and pull request.

## Build on it

Forks are welcome. Some easy places to start:

- **New output type**: add a `src/agents/writing/<name>.py` with a mixin class, add it to `WritingAgent`, and register the mode in `src/main.py`.
- **New model provider**: add a class with a `generate()` method in `src/core/model_provider.py`.
- **A frontend**: the API already allows a local dev server on ports 3000 to 3002 (CORS).

## License

[MIT](LICENSE). Use it, change it, ship it. Just keep the license notice.

Found a security problem? Please report it privately, see [SECURITY.md](SECURITY.md).
