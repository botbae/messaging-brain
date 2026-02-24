# Writing Agent v1 — Project Brief

## Goal
Build a writing agent that produces sellable UX + marketing + content outputs. Later sell it as a service.

## Current status (as of tonight)
- Python venv working
- Repo initialized + commits done
- No API keys stored (Anthropic key rotated and removed)
- Working scripts:
  - `src/writing_agent.py` generates a simple landing page draft
  - `src/main.py` is the entrypoint

## How to run
- Landing page draft:
  - `PROMPT="AI UX writing assistant" python src/main.py`

## Constraints
- No external LLM APIs for now (work in mock / structured templates).
- Keep it terminal-first; UI later.

## Next steps (tomorrow)
1) Add a proper client brief input:
   - product, audience, pain, offer, tone, CTA, examples
2) Add a critique + rewrite loop:
   - Draft v1 → Critic feedback → Draft v2
3) Add output modes:
   - landing page, LinkedIn post, UX microcopy set, email sequence
4) Decide framework later (CrewAI/LangGraph) only if needed.
