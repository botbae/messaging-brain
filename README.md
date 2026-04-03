# Unimind Backend

FastAPI app. Runs at localhost:8001.

## Setup
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # add your API keys
uvicorn src.api.app:app --reload --port 8001

## Environment variables
See .env.example for required keys.
Default provider is Ollama (free, local). Set UNIMIND_MODEL_PROVIDER=anthropic for Claude.

## Key files
- src/api/app.py — all API endpoints
- src/agents/writing_agent.py — landing blueprint generation
- src/core/model_provider.py — LLM provider abstraction (Ollama, Anthropic, OpenAI)
- src/core/confidence_engine.py — brain field scoring
- src/schemas/ — Pydantic output schemas

## Active endpoints
- POST /idea — extract messaging brain from raw idea
- POST /brain/save — save edited brain fields
- POST /generate/landing — generate landing page blueprint
- GET /client/{slug}/confidence — get confidence report
