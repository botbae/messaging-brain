"""Shared test setup.

Tests never call a real model. The LLM is replaced with a stub that fails,
so every writer exercises its rule-based fallback, which is deterministic.
Each test also runs in its own temp folder, so nothing is written to the repo.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _no_llm(*args, **kwargs):
    raise ConnectionError("LLM disabled in tests")


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    """Disable the model and work inside an empty temp folder."""
    import core.model_provider as mp

    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("UNIMIND_MODEL_PROVIDER", raising=False)
    monkeypatch.setattr(mp, "_ollama_generate", _no_llm)
    monkeypatch.chdir(tmp_path)
    yield


@pytest.fixture
def sample_brief_dict():
    return json.loads((REPO_ROOT / "briefs" / "sample.json").read_text())


@pytest.fixture
def sample_brief(sample_brief_dict):
    from agents.writing_agent import ClientBrief

    return ClientBrief(**sample_brief_dict)
