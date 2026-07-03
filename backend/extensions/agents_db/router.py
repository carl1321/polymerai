"""Agents API (DB-backed), ported from agentic_workflow.

This replaces the older file-based agents API in src.gateway.routers.agents.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, model_validator

from deerflow.skills import load_skills
from extensions._core.agent_request import AgentCreate, AgentListResponse, AgentResponse, AgentUpdate
from extensions._core.agents_db import (
    create_agent as db_create_agent,
)
from extensions._core.agents_db import (
    delete_agent as db_delete_agent,
)
from extensions._core.agents_db import (
    get_agent as db_get_agent,
)
from extensions._core.agents_db import (
    get_agent_by_name as db_get_agent_by_name,
)
from extensions._core.agents_db import (
    list_agents as db_list_agents,
)
from extensions._core.agents_db import (
    list_swarm_member_ids as db_list_swarm_member_ids,
)
from extensions._core.agents_db import (
    list_swarm_members_bulk as db_list_swarm_members_bulk,
)
from extensions._core.agents_db import (
    replace_swarm_members as db_replace_swarm_members,
)
from extensions._core.agents_db import (
    update_agent as db_update_agent,
)
from extensions._core.app_db import get_app_db_connection
from extensions._core.db_errors import is_undefined_table
from extensions._core.llms.llm import get_llm_by_model_name, get_llm_by_type
from extensions.auth.dependencies import CurrentUser, get_current_user_optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["agents"])

AGENT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9-]+$")
FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
AGENT_KIND_DEDICATED = "dedicated"
AGENT_KIND_SWARM = "swarm"
SUPPORTED_AGENT_KINDS = {AGENT_KIND_DEDICATED, AGENT_KIND_SWARM}


class GeneratePromptRequest(BaseModel):
    model_name: str | None = Field(default=None, description="Optional model override for generation and semantic rerank")
    max_skills: int = Field(default=3, ge=1, le=8, description="Maximum number of related skills to select")


class AgentChatRequest(BaseModel):
    """Aligned with ``POST /api/threads/{id}/runs/stream`` body (input + context + config)."""

    message: str | None = Field(
        default=None,
        description="Shortcut user text; ignored when ``messages`` is set. Serialized like the web UI: human + text blocks.",
    )
    messages: list[dict[str, Any]] | None = Field(
        default=None,
        description="Full ``input.messages`` array (same shape as LangGraph / useStream).",
    )
    thread_id: str | None = Field(
        default=None,
        description="Optional thread id for multi-turn; omit to start a new conversation",
    )
    model_name: str | None = Field(default=None, description="LLM id from config.yaml, e.g. doubao-seed-2.0")
    model: str | None = Field(default=None, description="Alias of model_name for lead_agent configurable")
    mode: str | None = Field(
        default=None,
        description='Product mode: "flash" | "pro" | "ultra" | "thinking" — expands flags like the workspace UI',
    )
    reasoning_effort: str | None = None
    thinking_enabled: bool | None = None
    is_plan_mode: bool | None = None
    subagent_enabled: bool | None = None
    max_concurrent_subagents: int | None = Field(default=None, ge=1, le=50)
    recursion_limit: int = Field(default=1000, ge=1, le=100000)

    @model_validator(mode="after")
    def _message_or_messages(self):
        if self.messages:
            return self
        if self.message is not None and str(self.message).strip():
            return self
        raise ValueError("Provide a non-empty message or messages[]")


def _runtime_context_from_chat_body(body: AgentChatRequest, *, agent_id: str) -> dict[str, Any]:
    """Mirror frontend ``useSubmitThread`` context expansion for mode flash/pro/ultra/thinking."""
    ctx: dict[str, Any] = {"agent_id": agent_id}

    resolved_model = body.model_name or body.model
    if resolved_model:
        ctx["model_name"] = resolved_model

    mode_raw = (body.mode or "").strip().lower()
    if mode_raw:
        ctx["mode"] = body.mode
        if body.thinking_enabled is None:
            ctx["thinking_enabled"] = mode_raw != "flash"
        if body.is_plan_mode is None:
            ctx["is_plan_mode"] = mode_raw in ("pro", "ultra")
        if body.subagent_enabled is None:
            ctx["subagent_enabled"] = mode_raw == "ultra"
        if body.reasoning_effort is None:
            if mode_raw == "ultra":
                ctx["reasoning_effort"] = "high"
            elif mode_raw == "pro":
                ctx["reasoning_effort"] = "medium"
            elif mode_raw == "thinking":
                ctx["reasoning_effort"] = "low"

    if body.thinking_enabled is not None:
        ctx["thinking_enabled"] = body.thinking_enabled
    if body.is_plan_mode is not None:
        ctx["is_plan_mode"] = body.is_plan_mode
    if body.subagent_enabled is not None:
        ctx["subagent_enabled"] = body.subagent_enabled
    if body.reasoning_effort is not None:
        ctx["reasoning_effort"] = body.reasoning_effort
    if body.max_concurrent_subagents is not None:
        ctx["max_concurrent_subagents"] = body.max_concurrent_subagents

    return ctx


class AgentChatResponse(BaseModel):
    answer: str
    thread_id: str
    run_id: str | None = None


class MatchedSkill(BaseModel):
    name: str
    reason: str | None = None


class GeneratePromptResponse(BaseModel):
    supplement_prompt: str
    skill_names: list[str]
    matched_skills: list[MatchedSkill]
    guardrail_report: dict[str, Any] | None = None


def _require_user(user: CurrentUser | None) -> CurrentUser:
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def _extract_answer_from_channel_values(values: dict[str, Any]) -> str:
    """Pick the last assistant message text from serialized checkpoint values."""
    messages = values.get("messages")
    if not isinstance(messages, list):
        return ""
    for msg in reversed(messages):
        if not isinstance(msg, dict):
            continue
        mtype = str(msg.get("type") or "")
        role = str(msg.get("role") or "")
        if mtype not in ("ai", "assistant") and role != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    if block.get("type") == "text":
                        t = block.get("text")
                        if isinstance(t, str):
                            parts.append(t)
                    elif isinstance(block.get("text"), str):
                        parts.append(block["text"])
            return "".join(parts)
    return ""


def _row_to_response(row: dict[str, Any]) -> AgentResponse:
    return AgentResponse(**row)


def _normalize_kind(kind: str | None) -> str:
    normalized = (kind or AGENT_KIND_DEDICATED).strip().lower()
    if normalized not in SUPPORTED_AGENT_KINDS:
        raise HTTPException(status_code=422, detail=f"Unsupported agent kind '{kind}'")
    return normalized


def _parse_member_ids(member_ids: list[str] | None) -> list[UUID]:
    if not member_ids:
        return []
    out: list[UUID] = []
    seen: set[UUID] = set()
    for raw in member_ids:
        try:
            uid = UUID(str(raw))
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Invalid member agent id '{raw}'") from exc
        if uid in seen:
            continue
        seen.add(uid)
        out.append(uid)
    return out


def _get_member_ids_from_request(request: AgentCreate | AgentUpdate) -> list[str] | None:
    value = getattr(request, "member_dedicated_ids", None)
    if value is None:
        return None
    if not isinstance(value, list):
        raise HTTPException(status_code=422, detail="member_dedicated_ids must be a list")
    return [str(v) for v in value]


def _validate_swarm_payload(kind: str, request: AgentCreate | AgentUpdate) -> None:
    if kind != AGENT_KIND_SWARM:
        return
    if request.skill_names:
        raise HTTPException(status_code=422, detail="swarm agent cannot bind skill_names directly")
    if request.workflow_ids:
        raise HTTPException(status_code=422, detail="swarm agent cannot bind workflow_ids directly")
    if request.default_workflow_id:
        raise HTTPException(status_code=422, detail="swarm agent cannot bind default_workflow_id")


def _validate_swarm_members(
    conn,
    *,
    swarm_id: UUID,
    member_ids: list[UUID],
    user: CurrentUser,
) -> None:
    if not member_ids:
        return
    org_id = str(user.organization_id) if user.organization_id else None
    user_id = str(user.id)
    for member_id in member_ids:
        if member_id == swarm_id:
            raise HTTPException(status_code=422, detail="swarm agent cannot include itself as member")
        row = db_get_agent(conn, member_id, user_id=user_id, organization_id=org_id)
        if not row:
            raise HTTPException(status_code=422, detail=f"Member agent {member_id} not found or inaccessible")
        member_kind = _normalize_kind(row.get("kind"))
        if member_kind != AGENT_KIND_DEDICATED:
            raise HTTPException(status_code=422, detail=f"Member agent {member_id} must be dedicated")


def _enrich_members(conn, row: dict[str, Any]) -> dict[str, Any]:
    agent = dict(row)
    kind = _normalize_kind(agent.get("kind"))
    if kind == AGENT_KIND_SWARM and agent.get("id"):
        agent["member_dedicated_ids"] = db_list_swarm_member_ids(conn, UUID(str(agent["id"])))
    else:
        agent["member_dedicated_ids"] = []
    return agent


def _get_llm(model_name: str | None):
    if model_name and model_name.strip():
        return get_llm_by_model_name(model_name.strip())
    return get_llm_by_type("basic")


def _response_to_text(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    chunks.append(text)
            elif isinstance(item, str):
                chunks.append(item)
        return "\n".join(chunks)
    return str(content)


def _extract_json_object(text: str) -> dict[str, Any]:
    if not text.strip():
        return {}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
    return {}


def _extract_supplement_prompt(text: str) -> str:
    """Best-effort parse for supplement prompt from model output."""
    payload = _extract_json_object(text)
    value = payload.get("supplement_prompt") if isinstance(payload, dict) else None
    if isinstance(value, str) and value.strip():
        return value.strip()
    # Fallback: accept plain text output (strip common markdown fences).
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json|markdown|md|text)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _normalize_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip())


def _remove_duplicate_lines(supplement: str, baselines: list[str]) -> tuple[str, int]:
    baseline_lines = {_normalize_line(line) for baseline in baselines for line in baseline.splitlines() if _normalize_line(line)}
    cleaned_lines: list[str] = []
    removed = 0
    for line in supplement.splitlines():
        norm = _normalize_line(line)
        if norm and norm in baseline_lines:
            removed += 1
            continue
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines).strip()
    return cleaned, removed


def _strip_frontmatter(markdown: str) -> str:
    return FRONTMATTER_RE.sub("", markdown, count=1).strip()


def _read_skill_baseline(skill_name: str, body_limit: int = 5000) -> str:
    skills = load_skills(enabled_only=False)
    for skill in skills:
        if skill.name != skill_name:
            continue
        raw = skill.skill_file.read_text(encoding="utf-8")
        body = _strip_frontmatter(raw)
        if len(body) > body_limit:
            return body[:body_limit]
        return body
    return ""


@router.get("/agents/check")
async def check_agent_name(name: str) -> dict[str, Any]:
    """Validate agent name format and check availability in DB.

    This preserves the legacy /api/agents/check?name= API used by the
    conversational bootstrap UI.
    """
    if not AGENT_NAME_PATTERN.match(name):
        raise HTTPException(
            status_code=422,
            detail="Invalid agent name. Must match ^[A-Za-z0-9-]+$ (letters, digits, and hyphens only).",
        )

    normalized = name.lower()
    conn = get_app_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM agents WHERE lower(name) = %s",
                (normalized,),
            )
            row = cur.fetchone()
            taken = bool(row and row["cnt"] > 0)
        return {"available": not taken, "name": normalized}
    finally:
        conn.close()


@router.get("/agents", response_model=AgentListResponse)
async def list_agents_api(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    name: str | None = Query(None),
    kind: str | None = Query(None),
    include_total: bool = Query(
        False,
        description="When true, run COUNT(*) and full lightweight rows + swarm members. Default false: skip COUNT, minimal columns, total≈offset+len (exact on last page only).",
    ),
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> AgentListResponse:
    """List agents with simple pagination and optional name filter."""
    user = _require_user(current_user)
    conn = get_app_db_connection()
    try:
        offset = (page - 1) * page_size
        try:
            agents, total = db_list_agents(
                conn,
                limit=page_size,
                offset=offset,
                name_like=name,
                kind=_normalize_kind(kind) if kind else None,
                user_id=str(user.id),
                organization_id=str(user.organization_id) if user.organization_id else None,
                lightweight=True,
                include_total=include_total,
                list_page=not include_total,
            )
        except Exception as e:
            if is_undefined_table(e):
                logger.warning("agents table missing, returning empty list: %s", e)
                return AgentListResponse(agents=[], total=0, limit=page_size, offset=offset)
            raise
        members_by_swarm: dict[str, list[str]] = {}
        if include_total:
            swarm_ids: list[UUID] = []
            for a in agents:
                if _normalize_kind(a.get("kind")) != AGENT_KIND_SWARM:
                    continue
                raw_id = a.get("id")
                if not raw_id:
                    continue
                try:
                    swarm_ids.append(UUID(str(raw_id)))
                except (ValueError, TypeError):
                    continue
            members_by_swarm = db_list_swarm_members_bulk(conn, swarm_ids) if swarm_ids else {}
        response_agents: list[AgentResponse] = []
        for a in agents:
            row = dict(a)
            if include_total:
                k = _normalize_kind(row.get("kind"))
                if k == AGENT_KIND_SWARM and row.get("id"):
                    row["member_dedicated_ids"] = members_by_swarm.get(str(row["id"]), [])
                else:
                    row["member_dedicated_ids"] = []
            else:
                row["member_dedicated_ids"] = []
            response_agents.append(_row_to_response(row))
        return AgentListResponse(
            agents=response_agents,
            total=total,
            limit=page_size,
            offset=offset,
        )
    finally:
        conn.close()


@router.post("/agents", response_model=AgentResponse, status_code=201)
async def create_agent_api(
    request: AgentCreate,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> AgentResponse:
    """Create a new agent for the current user."""
    user = _require_user(current_user)
    conn = get_app_db_connection()
    try:
        kind = _normalize_kind(request.kind)
        _validate_swarm_payload(kind, request)
        from uuid import UUID as _UUID

        default_wf = _UUID(request.default_workflow_id) if request.default_workflow_id else None
        agent_id = db_create_agent(
            conn,
            user_id=str(user.id),
            organization_id=str(user.organization_id) if user.organization_id else None,
            department_id=str(user.department_id) if user.department_id else None,
            name=request.name,
            description=request.description,
            system_prompt=request.system_prompt,
            user_prompt_template=request.user_prompt_template,
            prompt_variables=request.prompt_variables,
            opener=request.opener,
            suggested_questions=request.suggested_questions,
            knowledge_base_ids=request.knowledge_base_ids,
            tool_names=request.tool_names,
            skill_names=request.skill_names,
            workflow_ids=request.workflow_ids,
            default_workflow_id=default_wf,
            model_name=request.model_name,
            model_parameters=request.model_parameters,
            avatar=request.avatar,
            run_mode=request.run_mode,
            kind=kind,
            memory_enabled=request.memory_enabled,
            requires_plan_confirmation=request.requires_plan_confirmation,
            visibility=request.visibility,
        )
        member_ids = _parse_member_ids(_get_member_ids_from_request(request))
        if kind == AGENT_KIND_SWARM and member_ids:
            _validate_swarm_members(conn, swarm_id=agent_id, member_ids=member_ids, user=user)
            db_replace_swarm_members(conn, agent_id, member_ids)
        conn.commit()
        agent = db_get_agent(
            conn,
            agent_id,
            user_id=str(user.id),
            organization_id=str(user.organization_id) if user.organization_id else None,
        )
        if not agent:
            raise HTTPException(status_code=500, detail="Failed to retrieve created agent")
        return _row_to_response(_enrich_members(conn, agent))
    finally:
        conn.close()


@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent_api(
    agent_id: str,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> AgentResponse:
    """Get a single agent by UUID id or by name (slug), matching workspace URLs."""
    user = _require_user(current_user)
    conn = get_app_db_connection()
    try:
        try:
            parsed_id = UUID(agent_id)
        except ValueError:
            agent = db_get_agent_by_name(
                conn,
                agent_id,
                user_id=str(user.id),
                organization_id=str(user.organization_id) if user.organization_id else None,
            )
        else:
            agent = db_get_agent(
                conn,
                parsed_id,
                user_id=str(user.id),
                organization_id=str(user.organization_id) if user.organization_id else None,
            )
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        return _row_to_response(_enrich_members(conn, agent))
    finally:
        conn.close()


@router.put("/agents/{agent_id}", response_model=AgentResponse)
async def update_agent_api(
    agent_id: str,
    request: AgentUpdate,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> AgentResponse:
    """Update an existing agent."""
    user = _require_user(current_user)
    conn = get_app_db_connection()
    try:
        uid = UUID(agent_id)
        existing = db_get_agent(
            conn,
            uid,
            user_id=str(user.id),
            organization_id=str(user.organization_id) if user.organization_id else None,
        )
        if not existing:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        existing_kind = _normalize_kind(existing.get("kind"))
        requested_kind = _normalize_kind(request.kind) if request.kind is not None else existing_kind
        if requested_kind != existing_kind:
            raise HTTPException(status_code=422, detail="Changing agent kind is not supported")
        _validate_swarm_payload(requested_kind, request)
        default_wf = UUID(request.default_workflow_id) if request.default_workflow_id is not None else None
        updated = db_update_agent(
            conn,
            uid,
            user_id=str(user.id),
            name=request.name,
            description=request.description,
            system_prompt=request.system_prompt,
            user_prompt_template=request.user_prompt_template,
            prompt_variables=request.prompt_variables,
            opener=request.opener,
            suggested_questions=request.suggested_questions,
            knowledge_base_ids=request.knowledge_base_ids,
            tool_names=request.tool_names,
            skill_names=request.skill_names,
            workflow_ids=request.workflow_ids,
            default_workflow_id=default_wf,
            model_name=request.model_name,
            model_parameters=request.model_parameters,
            avatar=request.avatar,
            run_mode=request.run_mode,
            kind=requested_kind if request.kind is not None else None,
            memory_enabled=request.memory_enabled,
            requires_plan_confirmation=request.requires_plan_confirmation,
            visibility=request.visibility,
        )
        if not updated:
            raise HTTPException(status_code=403, detail="Only the owner can edit this agent")
        member_ids_raw = _get_member_ids_from_request(request)
        if member_ids_raw is not None:
            if requested_kind != AGENT_KIND_SWARM:
                raise HTTPException(status_code=422, detail="Only swarm agent supports member_dedicated_ids")
            member_ids = _parse_member_ids(member_ids_raw)
            _validate_swarm_members(conn, swarm_id=uid, member_ids=member_ids, user=user)
            db_replace_swarm_members(conn, uid, member_ids)
        conn.commit()
        agent = db_get_agent(
            conn,
            uid,
            user_id=str(user.id),
            organization_id=str(user.organization_id) if user.organization_id else None,
        )
        if not agent:
            raise HTTPException(status_code=500, detail="Failed to retrieve updated agent")
        return _row_to_response(_enrich_members(conn, agent))
    finally:
        conn.close()


@router.delete("/agents/{agent_id}")
async def delete_agent_api(
    agent_id: str,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    """Delete an agent."""
    user = _require_user(current_user)
    conn = get_app_db_connection()
    try:
        uid = UUID(agent_id)
        existing = db_get_agent(
            conn,
            uid,
            user_id=str(user.id),
            organization_id=str(user.organization_id) if user.organization_id else None,
        )
        if not existing:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        deleted = db_delete_agent(conn, uid, user_id=str(user.id))
        if not deleted:
            raise HTTPException(status_code=403, detail="Only the owner can delete this agent")
        conn.commit()
        return {"success": True}
    finally:
        conn.close()


@router.post("/agents/{agent_id}/generate-prompt", response_model=GeneratePromptResponse)
async def generate_agent_prompt_api(
    agent_id: str,
    request: GeneratePromptRequest | None = None,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> GeneratePromptResponse:
    """Generate supplement prompt from agent name/description using semantic skill rerank."""
    user = _require_user(current_user)
    conn = get_app_db_connection()
    try:
        uid = UUID(agent_id)
        agent = db_get_agent(
            conn,
            uid,
            user_id=str(user.id),
            organization_id=str(user.organization_id) if user.organization_id else None,
        )
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        kind = _normalize_kind(agent.get("kind"))
        if kind == AGENT_KIND_SWARM:
            raise HTTPException(status_code=422, detail="generate-prompt is only supported for dedicated agents")

        title = (agent.get("name") or "").strip()
        description = (agent.get("description") or "").strip()
        if not title and not description:
            raise HTTPException(status_code=422, detail="Agent name/description is empty; cannot generate prompt")

        req = request or GeneratePromptRequest()

        all_skills = load_skills(enabled_only=False)
        skill_metadata = [{"name": s.name, "description": (s.description or "").strip()} for s in all_skills if s.name and s.description]
        if not skill_metadata:
            raise HTTPException(status_code=422, detail="No skills available for semantic matching")

        llm = _get_llm(req.model_name)

        rerank_system = '你是技能匹配器。输入是智能体标题/描述和skills元数据(name,description)。请只基于语义相关性返回最相关skills，输出JSON对象：{"matches":[{"name":"skill_name","reason":"简短原因"}]}。不要输出Markdown，不要附加解释。'
        rerank_user = {
            "agent": {"title": title, "description": description},
            "max_skills": req.max_skills,
            "skills": skill_metadata,
        }
        rerank_resp = llm.invoke(
            [
                SystemMessage(content=rerank_system),
                HumanMessage(content=json.dumps(rerank_user, ensure_ascii=False)),
            ]
        )
        rerank_text = _response_to_text(rerank_resp)
        rerank_json = _extract_json_object(rerank_text)
        raw_matches = rerank_json.get("matches") if isinstance(rerank_json.get("matches"), list) else []

        valid_names = {s["name"] for s in skill_metadata}
        matched: list[MatchedSkill] = []
        selected_names: list[str] = []
        for item in raw_matches:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str):
                continue
            name = name.strip()
            if not name or name not in valid_names or name in selected_names:
                continue
            selected_names.append(name)
            reason = item.get("reason")
            matched.append(MatchedSkill(name=name, reason=reason if isinstance(reason, str) else None))
            if len(selected_names) >= req.max_skills:
                break

        if not selected_names:
            # Conservative fallback: no auto-association when rerank result is invalid.
            selected_names = []
            matched = []

        baselines: list[str] = []
        for name in selected_names:
            content = _read_skill_baseline(name)
            if content:
                baselines.append(f"## {name}\n{content}")
        baseline_text = "\n\n".join(baselines)

        generate_system = (
            "你是智能体提示词补充生成器。请基于 agent 的标题与描述，生成“补充提示词”。"
            "注意：补充提示词不是基础技能规范的替代。"
            "如果提供了技能基线(SKILL.md节选)，你必须避免重复其已有规则，且不得给出相反指令。"
            "输出JSON对象："
            '{"supplement_prompt":"..."}。'
            "不要输出Markdown代码块。"
        )
        generate_user = {
            "agent": {"title": title, "description": description},
            "matched_skills": selected_names,
            "skill_baselines": baseline_text,
            "style": "concise",
        }
        gen_messages = [
            SystemMessage(content=generate_system),
            HumanMessage(content=json.dumps(generate_user, ensure_ascii=False)),
        ]
        gen_resp = llm.invoke(gen_messages)
        gen_text = _response_to_text(gen_resp)
        supplement_prompt = _extract_supplement_prompt(gen_text)
        if not supplement_prompt:
            retry_system = '你上次输出格式不符合要求。请严格仅输出 JSON 对象，且必须包含字符串字段 supplement_prompt。示例：{"supplement_prompt":"..."}'
            retry_resp = llm.invoke(
                [
                    SystemMessage(content=retry_system),
                    HumanMessage(content=json.dumps(generate_user, ensure_ascii=False)),
                ]
            )
            retry_text = _response_to_text(retry_resp)
            supplement_prompt = _extract_supplement_prompt(retry_text)
        if not supplement_prompt:
            raise HTTPException(status_code=502, detail="Model failed to generate supplement prompt")

        dedup_prompt, dedup_removed = _remove_duplicate_lines(supplement_prompt, baselines)
        final_prompt = dedup_prompt or supplement_prompt

        # Lightweight conflict guard: ask model to validate and rewrite if conflicting.
        conflict_checked = False
        if baseline_text:
            conflict_checked = True
            guard_system = '你是提示词审校器。判断 supplement_prompt 是否与 skill_baselines 冲突。若冲突请改写成不冲突版本。输出JSON对象：{"conflict_free":true,"revised_prompt":"...","reason":"..."}。'
            guard_user = {
                "skill_baselines": baseline_text,
                "supplement_prompt": final_prompt,
            }
            guard_resp = llm.invoke(
                [
                    SystemMessage(content=guard_system),
                    HumanMessage(content=json.dumps(guard_user, ensure_ascii=False)),
                ]
            )
            guard_text = _response_to_text(guard_resp)
            guard_json = _extract_json_object(guard_text)
            revised = guard_json.get("revised_prompt") if isinstance(guard_json.get("revised_prompt"), str) else ""
            if revised.strip():
                final_prompt = revised.strip()

        return GeneratePromptResponse(
            supplement_prompt=final_prompt,
            skill_names=selected_names,
            matched_skills=matched,
            guardrail_report={"dedup_removed": dedup_removed, "conflict_checked": conflict_checked},
        )
    finally:
        conn.close()


@router.post("/agents/{agent_id}/chat", response_model=AgentChatResponse)
async def agent_chat(
    agent_id: str,
    body: AgentChatRequest,
    request: Request,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> AgentChatResponse:
    """Run a single Q&A turn for a DB-configured dedicated agent (blocks until the reply is ready)."""
    from app.gateway.deps import get_checkpointer
    from app.gateway.routers.thread_runs import RunCreateRequest
    from app.gateway.services import start_run
    from deerflow.runtime import serialize_channel_values
    from deerflow.runtime.runs.schemas import RunStatus

    user = _require_user(current_user)
    try:
        uid = UUID(agent_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid agent_id") from None

    conn = get_app_db_connection()
    try:
        agent = db_get_agent(
            conn,
            uid,
            user_id=str(user.id),
            organization_id=str(user.organization_id) if user.organization_id else None,
        )
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        if _normalize_kind(agent.get("kind")) == AGENT_KIND_SWARM:
            raise HTTPException(status_code=422, detail="chat is only supported for dedicated agents")
    finally:
        conn.close()

    thread_id = str(body.thread_id).strip() if body.thread_id else str(uuid.uuid4())

    if body.messages:
        input_payload: dict[str, Any] = {"messages": body.messages}
    else:
        input_payload = {
            "messages": [
                {
                    "type": "human",
                    "content": [{"type": "text", "text": str(body.message).strip()}],
                }
            ]
        }

    run_body = RunCreateRequest(
        assistant_id="lead_agent",
        input=input_payload,
        context=_runtime_context_from_chat_body(body, agent_id=str(uid)),
        config={
            "configurable": {"thread_id": thread_id},
            "recursion_limit": body.recursion_limit,
        },
        on_disconnect="continue",
    )

    record = await start_run(run_body, thread_id, request, current_user=user)

    if record.task is not None:
        try:
            await record.task
        except asyncio.CancelledError:
            pass

    if record.status != RunStatus.success:
        detail = record.error or f"run status: {record.status.value}"
        raise HTTPException(status_code=502, detail=detail)

    checkpointer = get_checkpointer(request)
    cfg = {"configurable": {"thread_id": thread_id}}
    try:
        checkpoint_tuple = await checkpointer.aget_tuple(cfg)
        if checkpoint_tuple is not None:
            checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}
            channel_values = checkpoint.get("channel_values", {})
            values = serialize_channel_values(channel_values)
            answer = _extract_answer_from_channel_values(values)
            return AgentChatResponse(answer=answer, thread_id=thread_id, run_id=record.run_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception("agent chat: failed to read checkpoint for thread %s", thread_id)
    raise HTTPException(status_code=502, detail="Failed to read agent response")


@router.get("/agents/{agent_id}/members")
async def get_swarm_members_api(
    agent_id: str,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    user = _require_user(current_user)
    conn = get_app_db_connection()
    try:
        uid = UUID(agent_id)
        row = db_get_agent(
            conn,
            uid,
            user_id=str(user.id),
            organization_id=str(user.organization_id) if user.organization_id else None,
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        if _normalize_kind(row.get("kind")) != AGENT_KIND_SWARM:
            raise HTTPException(status_code=422, detail="Only swarm agents have members")
        return {"member_dedicated_ids": db_list_swarm_member_ids(conn, uid)}
    finally:
        conn.close()


class SwarmMembersUpdateRequest(BaseModel):
    member_dedicated_ids: list[str] = Field(default_factory=list)


@router.put("/agents/{agent_id}/members")
async def replace_swarm_members_api(
    agent_id: str,
    request: SwarmMembersUpdateRequest,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    user = _require_user(current_user)
    conn = get_app_db_connection()
    try:
        uid = UUID(agent_id)
        row = db_get_agent(
            conn,
            uid,
            user_id=str(user.id),
            organization_id=str(user.organization_id) if user.organization_id else None,
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        if _normalize_kind(row.get("kind")) != AGENT_KIND_SWARM:
            raise HTTPException(status_code=422, detail="Only swarm agents can manage members")
        member_ids = _parse_member_ids(request.member_dedicated_ids)
        _validate_swarm_members(conn, swarm_id=uid, member_ids=member_ids, user=user)
        db_replace_swarm_members(conn, uid, member_ids)
        conn.commit()
        return {"member_dedicated_ids": db_list_swarm_member_ids(conn, uid)}
    finally:
        conn.close()
