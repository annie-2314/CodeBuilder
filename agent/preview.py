"""Helpers for discovering HTML entry points and building standalone previews."""

from __future__ import annotations

import base64
import mimetypes
import re
from pathlib import Path
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


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _file_to_data_uri(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    mime = mime or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def build_standalone_html(project_dir: Path, entry: str) -> str:
    """
    Inline linked CSS/JS (and simple local image refs) so the app can run inside
    Streamlit without a separate uvicorn server — works on phones / shared links.
    """
    entry_path = (project_dir / entry).resolve()
    root = project_dir.resolve()
    if root not in entry_path.parents and entry_path != root:
        raise ValueError("Invalid entry path")
    if not entry_path.exists():
        raise FileNotFoundError(entry)

    html = _read_text(entry_path)
    base_dir = entry_path.parent

    def resolve_local(ref: str) -> Optional[Path]:
        ref = ref.strip().strip("\"'")
        if not ref or ref.startswith(("http://", "https://", "data:", "//", "mailto:", "#")):
            return None
        ref = ref.split("?")[0].split("#")[0]
        candidate = (base_dir / ref).resolve()
        if root not in candidate.parents and candidate != root:
            return None
        return candidate if candidate.is_file() else None

    # <link rel="stylesheet" href="...">
    def replace_css(match: re.Match[str]) -> str:
        full = match.group(0)
        href = match.group(1)
        path = resolve_local(href)
        if path is None:
            return full
        return f"<style>\n{_read_text(path)}\n</style>"

    html = re.sub(
        r'<link[^>]+href=["\']([^"\']+)["\'][^>]*>',
        replace_css,
        html,
        flags=re.IGNORECASE,
    )

    # <script src="..."></script>
    def replace_script(match: re.Match[str]) -> str:
        full = match.group(0)
        src = match.group(1)
        path = resolve_local(src)
        if path is None:
            return full
        return f"<script>\n{_read_text(path)}\n</script>"

    html = re.sub(
        r'<script[^>]+src=["\']([^"\']+)["\'][^>]*>\s*</script>',
        replace_script,
        html,
        flags=re.IGNORECASE,
    )

    # Local images -> data URIs
    def replace_img(match: re.Match[str]) -> str:
        full = match.group(0)
        src = match.group(1)
        path = resolve_local(src)
        if path is None:
            return full
        return full.replace(src, _file_to_data_uri(path), 1)

    html = re.sub(
        r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>',
        replace_img,
        html,
        flags=re.IGNORECASE,
    )

    # Ensure a basic document shell if agents omitted html/body tags
    if "<html" not in html.lower():
        html = f"<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>{html}</body></html>"

    return html
