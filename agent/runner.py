"""High-level runner that prepares a project folder and invokes the agent graph."""

from __future__ import annotations

import re
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from agent.config import get_settings
from agent.graph import build_agent
from agent.tools import get_project_root, set_project_root

ProgressCallback = Callable[[str, dict[str, Any]], None]


def slugify(value: str, max_len: int = 40) -> str:
    """Convert free text into a filesystem-safe slug."""
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-") or "project"
    return value[:max_len].rstrip("-")


def create_project_dir(prompt: str) -> Path:
    """
    Create an isolated folder for one generation run.

    Suggested layout: generated_projects/<slug>_<yyyymmdd-hhmmss>_<id>/
    Keeps concurrent runs and downloads from colliding.
    """
    settings = get_settings()
    settings.projects_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    short_id = uuid.uuid4().hex[:8]
    folder = settings.projects_root / f"{slugify(prompt)}_{stamp}_{short_id}"
    folder.mkdir(parents=True, exist_ok=False)
    return folder


def list_project_files(project_dir: Path) -> list[str]:
    if not project_dir.exists():
        return []
    return sorted(
        str(path.relative_to(project_dir)).replace("\\", "/")
        for path in project_dir.rglob("*")
        if path.is_file()
    )


def zip_project(project_dir: Path, zip_path: Optional[Path] = None) -> Path:
    """Create a zip archive of the generated project for download."""
    if zip_path is None:
        zip_path = project_dir.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in project_dir.rglob("*"):
            if file_path.is_file():
                archive.write(file_path, arcname=file_path.relative_to(project_dir))
    return zip_path


def run_generation(
    user_prompt: str,
    model: Optional[str] = None,
    recursion_limit: Optional[int] = None,
    on_progress: Optional[ProgressCallback] = None,
    project_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """
    Run planner → architect → coder and write files under an isolated project folder.

    Returns a result dict with plan, paths, and generated file list.
    """
    settings = get_settings()
    project_path = project_dir or create_project_dir(user_prompt)
    set_project_root(project_path)

    events: list[dict[str, Any]] = []

    def _progress(stage: str, payload: dict[str, Any]) -> None:
        event = {"stage": stage, **payload}
        events.append(event)
        if on_progress:
            on_progress(stage, payload)

    agent = build_agent(model=model, on_progress=_progress)
    final_state = agent.invoke(
        {"user_prompt": user_prompt},
        {"recursion_limit": recursion_limit or settings.agent_recursion_limit},
    )

    files = list_project_files(project_path)
    archive = zip_project(project_path) if files else None

    plan = final_state.get("plan")
    task_plan = final_state.get("task_plan")

    return {
        "status": final_state.get("status", "DONE"),
        "user_prompt": user_prompt,
        "model": model or settings.groq_default_model,
        "project_dir": str(project_path),
        "project_name": project_path.name,
        "files": files,
        "zip_path": str(archive) if archive else None,
        "plan": plan.model_dump() if plan is not None else None,
        "task_plan": task_plan.model_dump() if task_plan is not None else None,
        "events": events,
    }


def delete_project(project_name: str) -> bool:
    """Remove a generated project folder and its zip if present."""
    settings = get_settings()
    target = (settings.projects_root / project_name).resolve()
    root = settings.projects_root.resolve()
    if root not in target.parents and target != root:
        raise ValueError("Invalid project path")
    removed = False
    if target.exists() and target.is_dir():
        shutil.rmtree(target)
        removed = True
    zip_path = target.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
        removed = True
    return removed


def resolve_project_dir(project_name: str) -> Path:
    settings = get_settings()
    target = (settings.projects_root / project_name).resolve()
    root = settings.projects_root.resolve()
    if root not in target.parents and target != root:
        raise ValueError("Invalid project path")
    if not target.exists():
        raise FileNotFoundError(f"Project not found: {project_name}")
    return target


# Re-export for callers that need the active root after a run
__all__ = [
    "create_project_dir",
    "delete_project",
    "get_project_root",
    "list_project_files",
    "resolve_project_dir",
    "run_generation",
    "slugify",
    "zip_project",
]
