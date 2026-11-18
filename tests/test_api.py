import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client():
    from api.app import app

    return TestClient(app)


def test_brain_then_generate(client, sample_brief_dict):
    r = client.post("/brain", json={"client": "acme", "brief": sample_brief_dict})
    assert r.status_code == 200, r.text  # regression: used to return 500
    assert r.json()["product_profile"]["product"] == sample_brief_dict["product"]

    for mode in ("landing", "linkedin", "ux", "positioning"):
        r = client.post(f"/generate/{mode}", json={"client": "acme"})
        assert r.status_code == 200, (mode, r.text)
        assert r.json()["text"].strip()

    r = client.get("/client/acme/confidence")
    assert r.status_code == 200
    assert "overall_score" in r.json()


@pytest.mark.parametrize("bad", ["/tmp/evil", "../escape", "a/b", "has space"])
def test_unsafe_client_names_are_rejected(client, sample_brief_dict, bad):
    r = client.post("/brain", json={"client": bad, "brief": sample_brief_dict})
    assert r.status_code == 400


def test_unknown_mode_is_rejected(client):
    assert client.post("/generate/nope", json={"client": "acme"}).status_code == 400


def test_idea_reports_missing_model(client):
    r = client.post("/idea", json={"idea": "a reminder app for dentists"})
    assert r.status_code == 500
    assert "Ollama" in r.json()["detail"]


def test_generation_errors_do_not_leak_details(client, sample_brief_dict, monkeypatch):
    import api.app as app_module

    client.post("/brain", json={"client": "acme", "brief": sample_brief_dict})

    def boom(*args, **kwargs):
        raise RuntimeError("secret internal path /home/someone/clients/acme")

    monkeypatch.setattr(app_module, "_run_generate", boom)
    r = client.post("/generate/positioning", json={"client": "acme"})
    assert r.status_code == 500
    assert r.json()["error"] == "generation_failed"
    assert "/home/someone" not in r.text
