"""Model provider abstraction for Messaging Brain.

The active provider is selected via the MODEL_PROVIDER environment variable
(or a .env file in the repo root):
    MODEL_PROVIDER=ollama      (default: local Ollama, free)
    MODEL_PROVIDER=anthropic   (all agents use Anthropic Claude)
    MODEL_PROVIDER=openai      (all agents use OpenAI)
    MODEL_PROVIDER=mixed       (per-agent routing via AGENT_MODEL_MAP)

UNIMIND_MODEL_PROVIDER (the project's old name) is still honoured as a fallback.

Usage (anywhere in the codebase):
    from core.model_provider import generate
    text = generate(system="...", user="...", model="llama3:8b", temperature=0.3)

Optional agent_name routes the call when MODEL_PROVIDER=mixed:
    text = generate(system="...", user="...", agent_name="writing")
"""

import os

try:  # Load a local .env file if python-dotenv is installed. Never required.
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

from core.llm import generate as _ollama_generate

# ---------------------------------------------------------------------------
# Per-agent model routing table (used when MODEL_PROVIDER=mixed)
# ---------------------------------------------------------------------------

AGENT_MODEL_MAP: dict[str, dict[str, str]] = {
    "extraction":     {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
    "structuring":    {"provider": "ollama",    "model": "llama3:8b"},
    "writing":        {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
    "critic":         {"provider": "ollama",    "model": "llama3:8b"},
    "fact_guard":     {"provider": "ollama",    "model": "llama3:8b"},
    "recommendation": {"provider": "ollama",    "model": "llama3:8b"},
}


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

class OllamaProvider:
    """Calls the local Ollama instance. Behaviour is identical to core.llm.generate."""

    def generate(self, system: str, user: str, model: str = "llama3:8b", temperature: float = 0.4) -> str:
        return _ollama_generate(system=system, user=user, model=model, temperature=temperature)


class AnthropicProvider:
    """Calls the Anthropic API using the anthropic SDK.

    Requires:
        - anthropic>=0.79.0 installed in the active environment
        - ANTHROPIC_API_KEY environment variable set

    Default model: claude-sonnet-4-20250514
    The `model` parameter passed to generate() is forwarded as-is to the API.
    """

    def __init__(self) -> None:
        try:
            import anthropic as _anthropic_sdk  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "The 'anthropic' package is required to use AnthropicProvider. "
                "Install it with: pip install anthropic>=0.79.0"
            ) from exc

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY environment variable is not set. "
                "Set it before using MODEL_PROVIDER=anthropic."
            )

        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)

    def generate(
        self,
        system: str,
        user: str,
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.4,
    ) -> str:
        message = self._client.messages.create(
            model=model,
            max_tokens=4096,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return message.content[0].text


class OpenAIProvider:
    """Calls the OpenAI API using the openai SDK.

    Requires:
        - openai>=1.83.0 installed in the active environment
        - OPENAI_API_KEY environment variable set

    Default model: gpt-4o
    The `model` parameter passed to generate() is forwarded as-is to the API.
    """

    def __init__(self) -> None:
        try:
            import openai as _openai_sdk  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "The 'openai' package is required to use OpenAIProvider. "
                "Install it with: pip install openai>=1.83.0"
            ) from exc

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY environment variable is not set. "
                "Set it before using MODEL_PROVIDER=openai."
            )

        import openai
        self._client = openai.OpenAI(api_key=api_key)

    def generate(
        self,
        system: str,
        user: str,
        model: str = "gpt-4o",
        temperature: float = 0.4,
    ) -> str:
        response = self._client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------

def active_provider_name() -> str:
    """Provider name from MODEL_PROVIDER (or legacy UNIMIND_MODEL_PROVIDER), default ollama."""
    return (
        os.getenv("MODEL_PROVIDER")
        or os.getenv("UNIMIND_MODEL_PROVIDER")
        or "ollama"
    ).strip().lower()


def get_provider(provider_name: str | None = None):
    """Return a provider instance for the given name (or active env config).

    Resolution order for provider_name=None:
        1. MODEL_PROVIDER env var
        2. UNIMIND_MODEL_PROVIDER env var (legacy fallback)
        3. "ollama" (default)

    Supported names: ollama, anthropic, openai, mixed
    ("mixed" returns OllamaProvider as the default; routing is handled in generate())
    ("cloud" is accepted as a legacy alias for "anthropic")
    """
    if provider_name is None:
        provider_name = active_provider_name()

    if provider_name in ("ollama", "mixed"):
        return OllamaProvider()
    if provider_name in ("anthropic", "cloud"):
        return AnthropicProvider()
    if provider_name == "openai":
        return OpenAIProvider()

    raise ValueError(
        f"Unknown provider {provider_name!r}. "
        "Supported: ollama, anthropic, openai, mixed (via MODEL_PROVIDER)."
    )


def _resolve_mixed(agent_name: str, fallback_model: str) -> tuple[object, str]:
    """For mixed mode: return (provider_instance, model) for the given agent."""
    entry = AGENT_MODEL_MAP.get(agent_name)
    if entry is None:
        # Unknown agent — fall back to Ollama with the caller's model
        return OllamaProvider(), fallback_model

    provider_name = entry["provider"]
    model = entry["model"]

    if provider_name == "ollama":
        return OllamaProvider(), model
    if provider_name == "anthropic":
        return AnthropicProvider(), model
    if provider_name == "openai":
        return OpenAIProvider(), model

    return OllamaProvider(), fallback_model


# ---------------------------------------------------------------------------
# Public generate() — drop-in replacement for core.llm.generate
# ---------------------------------------------------------------------------

def generate(
    system: str,
    user: str,
    model: str = "llama3:8b",
    temperature: float = 0.4,
    agent_name: str | None = None,
) -> str:
    """Generate text using the configured model provider.

    Drop-in replacement for core.llm.generate — behaviour is identical when
    MODEL_PROVIDER=ollama (the default).

    agent_name (optional): when set and MODEL_PROVIDER=mixed, the call
    is routed to the provider and model specified in AGENT_MODEL_MAP for that
    agent. Ignored in all other modes.
    """
    mode = active_provider_name()

    if mode == "mixed" and agent_name is not None:
        provider, resolved_model = _resolve_mixed(agent_name, model)
        return provider.generate(system=system, user=user, model=resolved_model, temperature=temperature)

    return get_provider(mode).generate(system=system, user=user, model=model, temperature=temperature)
