"""Helpers for discovering HTML entry points for live preview."""

from __future__ import annotations

from typing import Optional


def find_preview_entry(files: list[str]) -> Optional[str]:
    """Pick the best HTML entry point for in-browser live preview."""
    normalized = [f.replace("\\", "/") for f in files]
    preferred = ("index.html", "index.htm", "app.html", "main.html")
    for name in preferred:
        if name in normalized:
            return name
    html_files = [f for f in normalized if f.lower().endswith((".html", ".htm"))]
    if not html_files:
        return None
    html_files.sort(key=lambda p: (p.count("/"), len(p)))
    return html_files[0]
