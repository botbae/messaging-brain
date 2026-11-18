"""Local LLM integration via Ollama (stdlib only: urllib + json)."""

import json
import os
import urllib.error
import urllib.request


def generate(
    system: str,
    user: str,
    model: str = "llama3:8b",
    temperature: float = 0.4,
) -> str:
    """Call Ollama /api/generate and return the response text. Raises on HTTP/JSON errors."""
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    url = f"{base}/api/generate"
    payload = {
        "model": model,
        "prompt": user,
        "system": system,
        "stream": False,
        "options": {"temperature": temperature},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = resp.read().decode("utf-8")
    out = json.loads(body)
    return (out.get("response") or "").strip()
