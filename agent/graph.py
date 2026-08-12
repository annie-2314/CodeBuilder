"""LangGraph multi-agent pipeline: planner → architect → coder (loop)."""

from __future__ import annotations

from typing import Any, Callable, Optional

from langchain_groq import ChatGroq
from langgraph.constants import END
from langgraph.graph import StateGraph
from langgraph.prebuilt import create_react_agent

from agent.config import get_settings
from agent.prompts import architect_prompt, coder_system_prompt, planner_prompt
from agent.states import CoderState, Plan, TaskPlan
from agent.tools import (
    get_current_directory,
    list_files,
    read_file,
    write_file,
)

ProgressCallback = Callable[[str, dict[str, Any]], None]


def build_llm(model: Optional[str] = None) -> ChatGroq:
    """Create a Groq chat model from settings / override."""
    settings = get_settings()
    if not settings.groq_api_key:
        raise ValueError(
            "GROQ_API_KEY is missing. Copy .env.example to .env and add your key."
        )
    return ChatGroq(
        model=model or settings.groq_default_model,
        api_key=settings.groq_api_key,
        temperature=settings.llm_temperature,
    )


def build_agent(
    model: Optional[str] = None,
    on_progress: Optional[ProgressCallback] = None,
):
    """Compile the planner → architect → coder LangGraph."""

    llm = build_llm(model)

    def _emit(stage: str, payload: Optional[dict[str, Any]] = None) -> None:
        if on_progress:
            on_progress(stage, payload or {})

    def planner_agent(state: dict) -> dict:
        """Convert user prompt into a structured Plan."""
        _emit("planner", {"message": "Analyzing request and drafting project plan..."})
        user_prompt = state["user_prompt"]
        resp = llm.with_structured_output(Plan).invoke(planner_prompt(user_prompt))
        if resp is None:
            raise ValueError("Planner did not return a valid response.")
        _emit(
            "planner_done",
            {
                "message": f"Plan ready: {resp.name}",
                "plan": resp.model_dump(),
            },
        )
        return {"plan": resp}

    def architect_agent(state: dict) -> dict:
        """Break Plan into ordered ImplementationTasks."""
        _emit("architect", {"message": "Breaking plan into engineering tasks..."})
        plan: Plan = state["plan"]
        resp = llm.with_structured_output(TaskPlan).invoke(
            architect_prompt(plan=plan.model_dump_json())
        )
        if resp is None:
            raise ValueError("Architect did not return a valid response.")
        resp.plan = plan
        _emit(
            "architect_done",
            {
                "message": f"{len(resp.implementation_steps)} implementation tasks ready",
                "task_count": len(resp.implementation_steps),
                "task_plan": resp.model_dump(),
            },
        )
        return {"task_plan": resp}

    def coder_agent(state: dict) -> dict:
        """Implement one task per invocation; loop until all tasks are done."""
        coder_state: CoderState | None = state.get("coder_state")
        if coder_state is None:
            coder_state = CoderState(task_plan=state["task_plan"], current_step_idx=0)

        steps = coder_state.task_plan.implementation_steps
        if coder_state.current_step_idx >= len(steps):
            _emit("done", {"message": "All files generated."})
            return {"coder_state": coder_state, "status": "DONE"}

        current_task = steps[coder_state.current_step_idx]
        step_num = coder_state.current_step_idx + 1
        _emit(
            "coder",
            {
                "message": f"Coding step {step_num}/{len(steps)}: {current_task.filepath}",
                "step": step_num,
                "total": len(steps),
                "filepath": current_task.filepath,
            },
        )

        existing_content = read_file.invoke({"path": current_task.filepath})
        system_prompt = coder_system_prompt()
        user_prompt = (
            f"Task: {current_task.task_description}\n"
            f"File: {current_task.filepath}\n"
            f"Existing content:\n{existing_content}\n"
            "Use write_file(path, content) to save your changes."
        )

        coder_tools = [read_file, write_file, list_files, get_current_directory]
        react_agent = create_react_agent(llm, coder_tools)
        react_agent.invoke(
            {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            }
        )

        coder_state.current_step_idx += 1
        return {"coder_state": coder_state, "status": "IN_PROGRESS"}

    graph = StateGraph(dict)
    graph.add_node("planner", planner_agent)
    graph.add_node("architect", architect_agent)
    graph.add_node("coder", coder_agent)

    graph.add_edge("planner", "architect")
    graph.add_edge("architect", "coder")
    graph.add_conditional_edges(
        "coder",
        lambda s: "END" if s.get("status") == "DONE" else "coder",
        {"END": END, "coder": "coder"},
    )
    graph.set_entry_point("planner")
    return graph.compile()
