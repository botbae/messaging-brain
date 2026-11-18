# Contributing

Thanks for helping! Small, focused pull requests are easiest to review.

## Getting set up

Needs Python 3.11 or newer.

```bash
git clone https://github.com/<your-username>/<your-fork>.git
cd <your-fork>
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env               # optional: pick a model provider or add keys
```

No model running? That's fine. The app falls back to templates, and the tests never call a model.

## Before you open a pull request

```bash
python -m pytest
```

CI runs the same tests on Python 3.11, 3.12 and 3.13 for every pull request.

## Ground rules

- **The brain is the source of truth.** Writers read decisions from the Messaging Brain (`product_profile.json`). Don't make a writer re-ask the model for audience, problem or positioning.
- **Always return something usable.** Every output keeps its rule-based template fallback for when the model fails twice or isn't running.
- **Keep the validators.** Required-section checks and the banned hype phrases ("revolutionize", "seamless", ...) are there on purpose. Don't loosen them to make a test pass.
- **Tests stay offline.** No test should need Ollama, an API key or the internet.
- **Never commit secrets or client data.** Keys go in `.env`. Generated `clients/`, `outputs/` and `qa_runs/` folders stay local.
- Prompt changes: describe what you tried and paste a short sample output (before and after) in the PR.

Looking for something to work on? See the ideas in [docs/parked_modules.md](docs/parked_modules.md), the "Build on it" section of the README, and issues labelled `good first issue`.

## Security issues

Please report them privately. See [SECURITY.md](SECURITY.md).
