import pytest

from core import model_provider as mp


def test_default_provider_is_ollama():
    assert mp.active_provider_name() == "ollama"
    assert isinstance(mp.get_provider(), mp.OllamaProvider)


def test_model_provider_env_wins_over_legacy(monkeypatch):
    monkeypatch.setenv("UNIMIND_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("MODEL_PROVIDER", "Ollama")
    assert mp.active_provider_name() == "ollama"


def test_legacy_env_still_works(monkeypatch):
    monkeypatch.setenv("UNIMIND_MODEL_PROVIDER", "mixed")
    assert mp.active_provider_name() == "mixed"


def test_unknown_provider_raises():
    with pytest.raises(ValueError):
        mp.get_provider("nope")


def test_cloud_provider_without_key_fails_clearly(monkeypatch):
    pytest.importorskip("anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(EnvironmentError):
        mp.get_provider("anthropic")
