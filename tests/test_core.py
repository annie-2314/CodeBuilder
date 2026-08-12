"""Unit tests for config, tools path safety, and runner helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.config import AVAILABLE_MODELS, Settings
from agent.runner import slugify, zip_project
from agent.tools import safe_path_for_project, set_project_root, write_file, read_file


def test_available_models_include_gpt_oss_and_qwen():
    assert "openai/gpt-oss-120b" in AVAILABLE_MODELS
    assert "qwen/qwen3.6-27b" in AVAILABLE_MODELS


def test_settings_projects_root_relative(tmp_path, monkeypatch):
    monkeypatch.setenv("GENERATED_PROJECTS_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    settings = Settings()
    assert settings.projects_root == tmp_path / "out"


def test_slugify():
    assert slugify("Build a Calculator App!!!") == "build-a-calculator-app"
    assert slugify("") == "project"


def test_safe_path_blocks_traversal(tmp_path):
    set_project_root(tmp_path)
    with pytest.raises(ValueError):
        safe_path_for_project("../outside.txt")


def test_write_and_read_file(tmp_path):
    set_project_root(tmp_path)
    result = write_file.invoke({"path": "src/app.js", "content": "console.log(1);"})
    assert result.startswith("WROTE:")
    assert read_file.invoke({"path": "src/app.js"}) == "console.log(1);"
    assert (tmp_path / "src" / "app.js").exists()


def test_find_preview_entry_prefers_index():
    from agent.preview import find_preview_entry

    assert find_preview_entry(["css/style.css", "index.html", "app.js"]) == "index.html"
    assert find_preview_entry(["pages/home.html", "readme.md"]) == "pages/home.html"
    assert find_preview_entry(["main.py", "requirements.txt"]) is None


def test_build_standalone_html_inlines_assets(tmp_path):
    from agent.preview import build_standalone_html

    (tmp_path / "style.css").write_text("body{color:red}", encoding="utf-8")
    (tmp_path / "app.js").write_text("window.__ok=true;", encoding="utf-8")
    (tmp_path / "index.html").write_text(
        "<!DOCTYPE html><html><head>"
        '<link rel="stylesheet" href="style.css">'
        "</head><body><h1>Hi</h1>"
        '<script src="app.js"></script>'
        "</body></html>",
        encoding="utf-8",
    )
    html = build_standalone_html(tmp_path, "index.html")
    assert "body{color:red}" in html
    assert "window.__ok=true;" in html
    assert 'href="style.css"' not in html
    assert 'src="app.js"' not in html


def test_zip_project(tmp_path):
    project = tmp_path / "demo"
    project.mkdir()
    (project / "index.html").write_text("<html></html>", encoding="utf-8")
    archive = zip_project(project)
    assert archive.exists()
    assert archive.suffix == ".zip"
