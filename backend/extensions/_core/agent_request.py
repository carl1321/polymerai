"""Pydantic request/response models for agents API.

Copied from agentic_workflow.src.server.agent_request and kept in sync
with the `agents` table schema defined in src.agents_db.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentCreate(BaseModel):
    """Request body for creating an agent."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    system_prompt: str | None = None
    user_prompt_template: str | None = None
    prompt_variables: list[dict[str, Any]] | None = Field(default_factory=list)
    opener: str | None = None
    suggested_questions: list[str] | None = Field(default_factory=list)
    knowledge_base_ids: list[str] | None = Field(default_factory=list)
    tool_names: list[str] | None = Field(default_factory=list)
    skill_names: list[str] | None = Field(default_factory=list)
    workflow_ids: list[str] | None = Field(default_factory=list)
    default_workflow_id: str | None = None
    model_name: str | None = None
    model_parameters: dict[str, Any] | None = None
    avatar: str | None = None
    run_mode: str | None = None
    kind: str | None = "dedicated"
    memory_enabled: bool | None = None
    member_dedicated_ids: list[str] | None = Field(default_factory=list)
    # Whether REQUIRES explicit plan confirmation in UI before running.
    requires_plan_confirmation: bool | None = None
    visibility: str | None = Field(default="user")


class AgentUpdate(BaseModel):
    """Partial update for an agent; all fields optional."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    system_prompt: str | None = None
    user_prompt_template: str | None = None
    prompt_variables: list[dict[str, Any]] | None = None
    opener: str | None = None
    suggested_questions: list[str] | None = None
    knowledge_base_ids: list[str] | None = None
    tool_names: list[str] | None = None
    skill_names: list[str] | None = None
    workflow_ids: list[str] | None = None
    default_workflow_id: str | None = None
    model_name: str | None = None
    model_parameters: dict[str, Any] | None = None
    avatar: str | None = None
    run_mode: str | None = None
    kind: str | None = None
    memory_enabled: bool | None = None
    requires_plan_confirmation: bool | None = None
    member_dedicated_ids: list[str] | None = None
    visibility: str | None = None


class AgentResponse(BaseModel):
    """Response model for a single agent."""

    id: str
    user_id: str | None = None
    name: str
    description: str | None = None
    system_prompt: str | None = None
    user_prompt_template: str | None = None
    prompt_variables: list[dict[str, Any]] | None = None
    opener: str | None = None
    suggested_questions: list[str] | None = None
    knowledge_base_ids: list[str] | None = None
    tool_names: list[str] | None = None
    skill_names: list[str] | None = None
    workflow_ids: list[str] | None = None
    default_workflow_id: str | None = None
    model_name: str | None = None
    model_parameters: dict[str, Any] | None = None
    avatar: str | None = None
    run_mode: str | None = None
    kind: str | None = None
    memory_enabled: bool | None = None
    member_dedicated_ids: list[str] | None = None
    requires_plan_confirmation: bool | None = None
    visibility: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class AgentListResponse(BaseModel):
    """Paginated list of agents."""

    agents: list[AgentResponse]
    total: int
    limit: int
    offset: int
