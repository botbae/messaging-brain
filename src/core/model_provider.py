"""Minimal model provider abstraction.

The active provider is selected via the MODEL_PROVIDER environment variable:
    MODEL_PROVIDER=ollama  (default — uses local Ollama at localhost:11434)
    MODEL_PROVIDER=cloud   (stub — not yet implemented)

Usage (anywhere in the codebase):
    from core.model_provider import generate
    text = generate(system="...", user="...", model="llama3:8b", temperature=0.3)
"""

import os

from core.llm import generate as _ollama_generate


class OllamaProvider:
    """Calls the local Ollama instance. Behaviour is identical to core.llm.generate."""

    def generate(self, system: str, user: str, model: str = "llama3:8b", temperature: float = 0.4) -> str:
        return _ollama_generate(system=system, user=user, model=model, temperature=temperature)


class CloudProviderStub:
    """Placeholder for a future cloud provider (e.g. Anthropic, OpenAI).

    Not implemented yet — raises NotImplementedError at call time so failures are obvious.
    To add a cloud provider: subclass this, implement generate(), and register it in get_provider().
    """

    def generate(self, system: str, user: str, model: str = "", temperature: float = 0.4) -> str:
        raise NotImplementedError(
            "Cloud provider is not yet implemented. "
            "Set MODEL_PROVIDER=ollama, or implement CloudProviderStub.generate()."
        )


def get_provider():
    """Return the active provider instance based on MODEL_PROVIDER env var."""
    name = os.getenv("MODEL_PROVIDER", "ollama").lower()
    if name == "ollama":
        return OllamaProvider()
    if name == "cloud":
        return CloudProviderStub()
    raise ValueError(f"Unknown MODEL_PROVIDER={name!r}. Supported: ollama, cloud.")


def generate(system: str, user: str, model: str = "llama3:8b", temperature: float = 0.4) -> str:
    """Generate text using the configured model provider.

    Drop-in replacement for core.llm.generate — behaviour is identical when
    MODEL_PROVIDER=ollama (the default).
    """
    return get_provider().generate(system=system, user=user, model=model, temperature=temperature)
