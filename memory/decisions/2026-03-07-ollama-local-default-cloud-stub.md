# Local Ollama as the active backend; cloud provider stubbed out

**Date:** 2026-03-07
**Status:** active

## Decision

The active LLM backend is a local Ollama instance at `localhost:11434` running `llama3:8b`. A `CloudProviderStub` class exists in `src/core/model_provider.py` but raises `NotImplementedError` — it is a hook, not an implementation.

## Why

- Local Ollama has zero API cost and no rate limits during development.
- The prompt-and-validate loop in the generators makes multiple LLM calls per run (first attempt + optional retry). At cloud API rates this would add latency and cost.
- The primary development workflow is offline-capable.
- The provider abstraction (`MODEL_PROVIDER` env var, `get_provider()`, `OllamaProvider`) is in place so switching to a cloud model does not require changes to any generator code.

## Alternatives considered

- **Anthropic / Claude API**: would produce higher-quality output but introduces API key management, cost per run, and network dependency. Deferred until the output quality gap with local models justifies it.
- **OpenAI API**: same tradeoffs as Anthropic.
- **Dual-provider (ollama + cloud fallback)**: rejected for now — adds logic complexity and the fallback condition (Ollama unavailable) is already handled by deterministic template fallbacks in each generator.

## When to reconsider

- When `llama3:8b` output quality is a consistent bottleneck that rule-based fallbacks cannot compensate for
- When the backend moves from CLI to an API/service layer where a managed cloud provider is more appropriate
- When a customer-facing deployment requires guaranteed uptime that a local model cannot provide
