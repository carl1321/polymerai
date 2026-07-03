"""Pydantic request/response models for agents API.

Copied from agentic_workflow.src.server.agent_request and kept in sync
with the `agents` table schema defined in src.agents_db.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AgentCreate(BaseModel):
    """Request body for creating an agent."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    user_prompt_template: Optional[str] = None
    prompt_variables: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    opener: Optional[str] = None
    suggested_questions: Optional[List[str]] = Field(default_factory=list)
    knowledge_base_ids: Optional[List[str]] = Field(default_factory=list)
    tool_names: Optional[List[str]] = Field(default_factory=list)
    skill_names: Optional[List[str]] = Field(default_factory=list)
    workflow_ids: Optional[List[str]] = Field(default_factory=list)
    default_workflow_id: Optional[str] = None
    model_name: Optional[str] = None
    model_parameters: Optional[Dict[str, Any]] = None
    avatar: Optional[str] = None
    run_mode: Optional[str] = None
    kind: Optional[str] = "dedicated"
    memory_enabled: Optional[bool] = None
    member_dedicated_ids: Optional[List[str]] = Field(default_factory=list)
    # Whether REQUIRES explicit plan confirmation in UI before running.
    requires_plan_confirmation: Optional[bool] = None
    visibility: Optional[str] = Field(default="user")


class AgentUpdate(BaseModel):
    """Partial update for an agent; all fields optional."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    user_prompt_template: Optional[str] = None
    prompt_variables: Optional[List[Dict[str, Any]]] = None
    opener: Optional[str] = None
    suggested_questions: Optional[List[str]] = None
    knowledge_base_ids: Optional[List[str]] = None
    tool_names: Optional[List[str]] = None
    skill_names: Optional[List[str]] = None
    workflow_ids: Optional[List[str]] = None
    default_workflow_id: Optional[str] = None
    model_name: Optional[str] = None
    model_parameters: Optional[Dict[str, Any]] = None
    avatar: Optional[str] = None
    run_mode: Optional[str] = None
    kind: Optional[str] = None
    memory_enabled: Optional[bool] = None
    requires_plan_confirmation: Optional[bool] = None
    member_dedicated_ids: Optional[List[str]] = None
    visibility: Optional[str] = None


class AgentResponse(BaseModel):
    """Response model for a single agent."""

    id: str
    user_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    user_prompt_template: Optional[str] = None
    prompt_variables: Optional[List[Dict[str, Any]]] = None
    opener: Optional[str] = None
    suggested_questions: Optional[List[str]] = None
    knowledge_base_ids: Optional[List[str]] = None
    tool_names: Optional[List[str]] = None
    skill_names: Optional[List[str]] = None
    workflow_ids: Optional[List[str]] = None
    default_workflow_id: Optional[str] = None
    model_name: Optional[str] = None
    model_parameters: Optional[Dict[str, Any]] = None
    avatar: Optional[str] = None
    run_mode: Optional[str] = None
    kind: Optional[str] = None
    memory_enabled: Optional[bool] = None
    member_dedicated_ids: Optional[List[str]] = None
    requires_plan_confirmation: Optional[bool] = None
    visibility: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AgentListResponse(BaseModel):
    """Paginated list of agents."""

    agents: List[AgentResponse]
    total: int
    limit: int
    offset: int

