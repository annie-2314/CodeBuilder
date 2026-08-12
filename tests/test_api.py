"""API smoke tests that do not call Groq."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.server import app
from agent.config import get_settings
from agent.preview import find_preview_entry

client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_models_endpoint():
    response = client.get("/api/models")
    assert response.status_code == 200
    payload = response.json()
    assert "models" in payload
    ids = {m["id"] for m in payload["models"]}
    assert "openai/gpt-oss-120b" in ids
    assert "qwen/qwen3.6-27b" in ids


def test_find_preview_entry_prefers_index():
    assert find_preview_entry(["css/style.css", "index.html", "app.js"]) == "index.html"
    assert find_preview_entry(["pages/home.html", "readme.md"]) == "pages/home.html"
    assert find_preview_entry(["main.py", "requirements.txt"]) is None


def test_live_preview_serves_html(tmp_path, monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("GENERATED_PROJECTS_DIR", str(tmp_path))
    get_settings.cache_clear()

    project = tmp_path / "demo-calc"
    project.mkdir()
    (project / "index.html").write_text(
        "<html><body><h1>Calc</h1><script src='app.js'></script></body></html>",
        encoding="utf-8",
    )
    (project / "app.js").write_text("console.log('ok');", encoding="utf-8")

    # Re-import settings path used by server module
    from api import server as server_module

    server_module.settings = get_settings()

    info = client.get("/api/projects/demo-calc/preview-info")
    assert info.status_code == 200
    assert info.json()["previewable"] is True
    assert info.json()["entry"] == "index.html"

    html = client.get("/api/projects/demo-calc/live/index.html")
    assert html.status_code == 200
    assert "Calc" in html.text
    assert "text/html" in html.headers.get("content-type", "")

    js = client.get("/api/projects/demo-calc/live/app.js")
    assert js.status_code == 200
    assert "console.log" in js.text

    root = client.get("/api/projects/demo-calc/live/", follow_redirects=False)
    assert root.status_code in {307, 302}
