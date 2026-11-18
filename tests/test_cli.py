import subprocess
import sys

from conftest import REPO_ROOT


def test_cli_landing_writes_versioned_output(tmp_path):
    env = {"PATH": "/usr/bin:/bin", "OLLAMA_BASE_URL": "http://127.0.0.1:9"}
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "src" / "main.py"),
         "--brief", str(REPO_ROOT / "briefs" / "sample.json"), "--mode", "landing"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, r.stderr
    out_dir = tmp_path / "outputs" / "ai-ux-writing-operator"
    assert (out_dir / "landing_v1.md").exists()
    assert (out_dir / "landing_latest.md").read_text().strip()


def test_cli_rejects_unsafe_client_name(tmp_path):
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "src" / "main.py"),
         "--client", "../escape", "--mode", "init_client"],
        cwd=tmp_path, env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 2
    assert "not a valid name" in r.stderr
    assert not (tmp_path.parent / "escape").exists()
