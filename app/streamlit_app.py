"""Streamlit UI for Code Buddy — generate, inspect, preview, and download projects."""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

# Ensure repo root is on sys.path so `agent` / `api` imports work under Streamlit.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st
import streamlit.components.v1 as components

from agent.config import AVAILABLE_MODELS, MODEL_LABELS, get_settings
from agent.preview import find_preview_entry
from agent.runner import list_project_files, run_generation

st.set_page_config(
    page_title="Code Buddy",
    page_icon="🛠️",
    layout="wide",
)

settings = get_settings()


def _ensure_key() -> bool:
    if not settings.groq_api_key or settings.groq_api_key.startswith("your_"):
        st.error(
            "GROQ_API_KEY is missing. Copy `.env.example` to `.env`, add your Groq key, "
            "then restart Streamlit."
        )
        return False
    return True


def _zip_bytes(project_dir: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in project_dir.rglob("*"):
            if file_path.is_file():
                archive.write(file_path, arcname=file_path.relative_to(project_dir))
    buffer.seek(0)
    return buffer.read()


def _live_preview_url(project_name: str, entry: str) -> str:
    host = "127.0.0.1" if settings.api_host in {"0.0.0.0", "::"} else settings.api_host
    return f"http://{host}:{settings.api_port}/api/projects/{project_name}/live/{entry}"


EXAMPLES = [
    "Build a calculator web app with add, subtract, multiply and divide",
    "Create a to-do list app with HTML, CSS, and JavaScript",
    "Create a simple blog API in FastAPI with SQLite",
]

st.title("Code Buddy")
st.caption(
    "Multi-agent coding assistant — Planner → Architect → Coder — powered by Groq"
)

if "prompt_input" not in st.session_state:
    st.session_state.prompt_input = ""

with st.sidebar:
    st.header("Settings")
    model_options = list(AVAILABLE_MODELS)
    default_idx = (
        model_options.index(settings.groq_default_model)
        if settings.groq_default_model in model_options
        else 0
    )
    model = st.selectbox(
        "LLM model",
        options=model_options,
        index=default_idx,
        format_func=lambda m: MODEL_LABELS.get(m, m),
    )

    st.divider()
    st.markdown("**Try an example**")
    for idx, example in enumerate(EXAMPLES):
        if st.button(example, key=f"example_prompt_{idx}", use_container_width=True):
            st.session_state.prompt_input = example
            st.rerun()

prompt = st.text_area(
    "Describe the project you want to build",
    height=120,
    placeholder="Build a calculator web app with add, subtract, multiply and divide buttons.",
    key="prompt_input",
)

col_run, col_clear = st.columns([1, 1])
run_clicked = col_run.button("Generate project", type="primary", use_container_width=True)
if col_clear.button("Clear result", use_container_width=True):
    for key in ("result", "events"):
        st.session_state.pop(key, None)
    st.rerun()

progress_box = st.empty()
log_box = st.empty()

if run_clicked:
    if not _ensure_key():
        st.stop()
    if not prompt or len(prompt.strip()) < 3:
        st.warning("Please enter a project description.")
        st.stop()

    events: list[str] = []

    def on_progress(stage: str, payload: dict) -> None:
        message = payload.get("message") or stage
        events.append(f"[{stage}] {message}")
        progress_box.info(message)
        log_box.code("\n".join(events), language="text")

    with st.spinner("Agents are working..."):
        try:
            result = run_generation(
                user_prompt=prompt.strip(),
                model=model,
                on_progress=on_progress,
            )
            st.session_state["result"] = result
            st.session_state["events"] = events
            progress_box.success("Project generated successfully.")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Generation failed: {exc}")
            st.stop()

result = st.session_state.get("result")
if result:
    st.subheader(f"Project: `{result['project_name']}`")
    st.write(f"Model: `{result['model']}` · Files: **{len(result['files'])}**")

    plan = result.get("plan") or {}
    if plan:
        with st.expander("Project plan", expanded=True):
            st.markdown(f"**{plan.get('name', '')}** — {plan.get('description', '')}")
            st.markdown(f"Tech stack: `{plan.get('techstack', '')}`")
            st.markdown("Features:")
            for feature in plan.get("features", []):
                st.markdown(f"- {feature}")
            st.markdown("Files:")
            for file_info in plan.get("files", []):
                st.markdown(f"- `{file_info.get('path')}` — {file_info.get('purpose')}")

    project_dir = Path(result["project_dir"])
    files = result.get("files") or list_project_files(project_dir)
    entry = find_preview_entry(files)

    dl_col, path_col = st.columns([1, 2])
    with dl_col:
        st.download_button(
            label="Download project ZIP",
            data=_zip_bytes(project_dir),
            file_name=f"{result['project_name']}.zip",
            mime="application/zip",
            use_container_width=True,
        )
    with path_col:
        st.code(str(project_dir), language="text")
        st.caption("Generated project folder")

    if entry:
        live_url = _live_preview_url(result["project_name"], entry)
        st.subheader("Live preview")
        st.link_button("Open live preview in new tab", live_url)
        components.iframe(live_url, height=560, scrolling=True)
    else:
        st.info("No HTML entry file found for live preview (e.g. index.html).")

    if files:
        selected = st.selectbox("Preview file", options=files)
        content = (project_dir / selected).read_text(encoding="utf-8")
        st.code(content, language=Path(selected).suffix.lstrip(".") or "text")

    if st.session_state.get("events"):
        with st.expander("Agent event log"):
            st.code("\n".join(st.session_state["events"]), language="text")
