"""Pydantic state models shared across planner, architect, and coder agents."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class File(BaseModel):
    path: str = Field(description="Relative path of the file to create or modify")
    purpose: str = Field(
        description="Purpose of the file, e.g. 'main application logic'"
    )


class Plan(BaseModel):
    name: str = Field(description="Name of the application to build")
    description: str = Field(description="One-line description of the application")
    techstack: str = Field(
        description="Tech stack, e.g. 'html, css, javascript' or 'fastapi, sqlite'"
    )
    features: list[str] = Field(description="List of features the app should include")
    files: list[File] = Field(
        description="Files to create, each with a path and purpose"
    )


class ImplementationTask(BaseModel):
    filepath: str = Field(description="Relative path of the file for this task")
    task_description: str = Field(
        description="Detailed, self-contained implementation instructions"
    )


class TaskPlan(BaseModel):
    implementation_steps: list[ImplementationTask] = Field(
        description="Ordered implementation steps for the coder agent"
    )
    model_config = ConfigDict(extra="allow")


class CoderState(BaseModel):
    task_plan: TaskPlan = Field(description="Full task plan being executed")
    current_step_idx: int = Field(
        default=0, description="Index of the current implementation step"
    )
    current_file_content: Optional[str] = Field(
        default=None, description="Content of the file currently being edited"
    )
