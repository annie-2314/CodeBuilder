"""Safe filesystem tools scoped to the active generated project root."""

from __future__ import annotations

import pathlib
import subprocess
from contextvars import ContextVar
from typing import Optional, Tuple

from langchain_core.tools import tool

_project_root: ContextVar[Optional[pathlib.Path]] = ContextVar(
    "project_root", default=None
)


def set_project_root(path: pathlib.Path) -> None:
    """Bind tools to a specific generated project directory for this run."""
    path.mkdir(parents=True, exist_ok=True)
    _project_root.set(path.resolve())


def get_project_root() -> pathlib.Path:
    root = _project_root.get()
    if root is None:
        raise RuntimeError(
            "Project root is not set. Call set_project_root() before using tools."
        )
    return root


def safe_path_for_project(path: str) -> pathlib.Path:
    """Resolve a relative path under the project root and block path traversal."""
    root = get_project_root()
    candidate = (root / path).resolve()
    if root not in candidate.parents and candidate != root:
        raise ValueError("Attempt to access a path outside the project root")
    return candidate


@tool
def write_file(path: str, content: str) -> str:
    """Writes content to a file at the specified path within the project root."""
    target = safe_path_for_project(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"WROTE:{target.relative_to(get_project_root())}"


@tool
def read_file(path: str) -> str:
    """Reads content from a file at the specified path within the project root."""
    target = safe_path_for_project(path)
    if not target.exists():
        return ""
    return target.read_text(encoding="utf-8")


@tool
def get_current_directory() -> str:
    """Returns the current project root directory."""
    return str(get_project_root())


@tool
def list_files(directory: str = ".") -> str:
    """Lists all files under a directory within the project root."""
    target = safe_path_for_project(directory)
    if not target.exists():
        return "No files found."
    if not target.is_dir():
        return f"ERROR: {directory} is not a directory"
    files = [
        str(f.relative_to(get_project_root()))
        for f in target.rglob("*")
        if f.is_file()
    ]
    return "\n".join(sorted(files)) if files else "No files found."


@tool
def run_cmd(cmd: str, cwd: str = ".", timeout: int = 30) -> Tuple[int, str, str]:
    """Runs a shell command inside the project root and returns exit code, stdout, stderr."""
    cwd_dir = safe_path_for_project(cwd)
    result = subprocess.run(
        cmd,
        shell=True,
        cwd=str(cwd_dir),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr
