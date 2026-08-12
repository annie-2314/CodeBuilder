"""FastAPI backend for the React UI and programmatic clients."""

from __future__ import annotations

import mimetypes
import threading
import traceback
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from agent.config import AVAILABLE_MODELS, MODEL_LABELS, get_settings
from agent.preview import find_preview_entry
from agent.runner import (
    create_project_dir,
    list_project_files,
    resolve_project_dir,
    run_generation,
    zip_project,
)

settings = get_settings()

app = FastAPI(
    title="Code Buddy API",
    description="Multi-agent coding assistant API (Planner → Architect → Coder)",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AllowLivePreviewFrameMiddleware(BaseHTTPMiddleware):
    """Allow the React/Streamlit UIs to embed generated apps in an iframe."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if "/live" in request.url.path:
            response.headers["Content-Security-Policy"] = "frame-ancestors *"
            # Starlette may set DENY elsewhere; clear for live preview assets.
            if "x-frame-options" in response.headers:
                del response.headers["x-frame-options"]
        return response


app.add_middleware(AllowLivePreviewFrameMiddleware)


def _resolve_project_or_http(project_name: str) -> Path:
    try:
        return resolve_project_dir(project_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _safe_project_file(project_dir: Path, file_path: str) -> Path:
    target = (project_dir / file_path).resolve()
    root = project_dir.resolve()
    if root not in target.parents and target != root:
        raise HTTPException(status_code=400, detail="Invalid file path")
    return target


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=3, description="Natural language project request")
    model: Optional[str] = Field(
        default=None,
        description="Groq model id; defaults to GROQ_DEFAULT_MODEL",
    )


class JobRecord(BaseModel):
    job_id: str
    status: JobStatus
    prompt: str
    model: str
    created_at: str
    updated_at: str
    project_name: Optional[str] = None
    project_dir: Optional[str] = None
    files: list[str] = Field(default_factory=list)
    zip_available: bool = False
    plan: Optional[dict[str, Any]] = None
    task_plan: Optional[dict[str, Any]] = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None


_jobs: dict[str, JobRecord] = {}
_lock = threading.Lock()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_model(model: Optional[str]) -> str:
    chosen = model or settings.groq_default_model
    if chosen not in AVAILABLE_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported model '{chosen}'. Choose one of: {list(AVAILABLE_MODELS)}",
        )
    return chosen


def _update_job(job_id: str, **kwargs: Any) -> None:
    with _lock:
        job = _jobs[job_id]
        data = job.model_dump()
        data.update(kwargs)
        data["updated_at"] = _utcnow()
        _jobs[job_id] = JobRecord(**data)


def _run_job(job_id: str, prompt: str, model: str) -> None:
    _update_job(job_id, status=JobStatus.running)

    def on_progress(stage: str, payload: dict[str, Any]) -> None:
        with _lock:
            job = _jobs[job_id]
            events = list(job.events)
            events.append({"stage": stage, **payload, "at": _utcnow()})
            _jobs[job_id] = job.model_copy(
                update={"events": events, "updated_at": _utcnow()}
            )

    try:
        project_dir = create_project_dir(prompt)
        _update_job(
            job_id,
            project_name=project_dir.name,
            project_dir=str(project_dir),
        )
        result = run_generation(
            user_prompt=prompt,
            model=model,
            on_progress=on_progress,
            project_dir=project_dir,
        )
        _update_job(
            job_id,
            status=JobStatus.completed,
            project_name=result["project_name"],
            project_dir=result["project_dir"],
            files=result["files"],
            zip_available=bool(result.get("zip_path")),
            plan=result.get("plan"),
            task_plan=result.get("task_plan"),
            events=result.get("events", []),
        )
    except Exception as exc:  # noqa: BLE001 - surface to client
        traceback.print_exc()
        _update_job(job_id, status=JobStatus.failed, error=str(exc))


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/models")
def models() -> dict[str, Any]:
    return {
        "default": settings.groq_default_model,
        "models": [
            {"id": model_id, "label": MODEL_LABELS.get(model_id, model_id)}
            for model_id in AVAILABLE_MODELS
        ],
    }


@app.post("/api/generate", response_model=JobRecord)
def generate(request: GenerateRequest, background_tasks: BackgroundTasks) -> JobRecord:
    if not settings.groq_api_key or settings.groq_api_key.startswith("your_"):
        raise HTTPException(
            status_code=400,
            detail="GROQ_API_KEY is not configured. Copy .env.example to .env and set your key.",
        )
    model = _validate_model(request.model)
    job_id = uuid.uuid4().hex
    now = _utcnow()
    job = JobRecord(
        job_id=job_id,
        status=JobStatus.queued,
        prompt=request.prompt.strip(),
        model=model,
        created_at=now,
        updated_at=now,
    )
    with _lock:
        _jobs[job_id] = job
    background_tasks.add_task(_run_job, job_id, job.prompt, model)
    return job


@app.get("/api/jobs/{job_id}", response_model=JobRecord)
def get_job(job_id: str) -> JobRecord:
    with _lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/projects")
def list_projects() -> dict[str, Any]:
    root = settings.projects_root
    root.mkdir(parents=True, exist_ok=True)
    projects = []
    for path in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if path.is_dir():
            files = list_project_files(path)
            projects.append(
                {
                    "name": path.name,
                    "files": files,
                    "zip_available": path.with_suffix(".zip").exists(),
                    "preview_entry": find_preview_entry(files),
                }
            )
    return {"projects": projects}


@app.get("/api/projects/{project_name}/preview-info")
def preview_info(project_name: str) -> dict[str, Any]:
    project_dir = _resolve_project_or_http(project_name)
    files = list_project_files(project_dir)
    entry = find_preview_entry(files)
    return {
        "project_name": project_name,
        "previewable": entry is not None,
        "entry": entry,
        "live_url": (
            f"/api/projects/{project_name}/live/{entry}" if entry else None
        ),
        "files": files,
    }


@app.get("/api/projects/{project_name}/live")
@app.get("/api/projects/{project_name}/live/")
def live_preview_root(project_name: str) -> RedirectResponse:
    project_dir = _resolve_project_or_http(project_name)
    entry = find_preview_entry(list_project_files(project_dir))
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail="No HTML entry file found for live preview (expected index.html).",
        )
    return RedirectResponse(
        url=f"/api/projects/{project_name}/live/{entry}",
        status_code=307,
    )


@app.get("/api/projects/{project_name}/live/{file_path:path}")
def live_preview_asset(project_name: str, file_path: str) -> Response:
    """Serve generated project assets so users can test apps in an iframe."""
    project_dir = _resolve_project_or_http(project_name)
    target = _safe_project_file(project_dir, file_path)
    if target.is_dir():
        index = target / "index.html"
        if index.exists():
            target = index
        else:
            raise HTTPException(status_code=404, detail="Directory has no index.html")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    media_type, _ = mimetypes.guess_type(str(target))
    return FileResponse(
        path=target,
        media_type=media_type or "application/octet-stream",
        filename=None,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": "frame-ancestors *",
        },
    )


@app.get("/api/projects/{project_name}/download")
def download_project(project_name: str) -> FileResponse:
    project_dir = _resolve_project_or_http(project_name)

    zip_path = project_dir.with_suffix(".zip")
    if not zip_path.exists():
        zip_path = zip_project(project_dir)
    return FileResponse(
        path=zip_path,
        filename=f"{project_name}.zip",
        media_type="application/zip",
    )


@app.get("/api/projects/{project_name}/files/{file_path:path}")
def read_project_file(project_name: str, file_path: str) -> dict[str, str]:
    project_dir = _resolve_project_or_http(project_name)
    target = _safe_project_file(project_dir, file_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return {"path": file_path, "content": target.read_text(encoding="utf-8")}


def create_app() -> FastAPI:
    return app
