"""Agents PostgreSQL storage: table DDL and CRUD operations.

Copied and adapted from agentic_workflow.src.server.agent_db.
This module expects an existing psycopg connection (see src.app_db.get_app_db_connection).
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)

_AGENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255),
    visibility VARCHAR(32) NOT NULL DEFAULT 'user',
    organization_id UUID,
    department_id UUID,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    system_prompt TEXT,
    user_prompt_template TEXT,
    prompt_variables JSONB DEFAULT '[]',
    opener TEXT,
    suggested_questions JSONB DEFAULT '[]',
    knowledge_base_ids JSONB DEFAULT '[]',
    tool_names JSONB DEFAULT '[]',
    skill_names JSONB DEFAULT '[]',
    workflow_ids JSONB DEFAULT '[]',
    default_workflow_id UUID,
    model_name VARCHAR(255),
    model_parameters JSONB,
    avatar TEXT,
    run_mode VARCHAR(64),
    kind VARCHAR(32) NOT NULL DEFAULT 'dedicated',
    memory_enabled BOOLEAN,
    requires_plan_confirmation BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agents_user_id ON agents(user_id);
CREATE INDEX IF NOT EXISTS idx_agents_org_visibility ON agents(organization_id, visibility);
CREATE INDEX IF NOT EXISTS idx_agents_name ON agents(name);
CREATE INDEX IF NOT EXISTS idx_agents_created_at ON agents(created_at DESC);

CREATE TABLE IF NOT EXISTS agent_swarm_members (
    swarm_agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    dedicated_agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    position INT,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (swarm_agent_id, dedicated_agent_id)
);
CREATE INDEX IF NOT EXISTS idx_swarm_members_swarm_id ON agent_swarm_members(swarm_agent_id);
CREATE INDEX IF NOT EXISTS idx_swarm_members_dedicated_id ON agent_swarm_members(dedicated_agent_id);
"""


def init_agents_table(conn) -> None:
    """Create agents table if it does not exist (idempotent).

    Call from offline migration tooling (e.g. ``scripts/init_app_database.py``), not from API/runtime code paths.
    """
    with conn.cursor() as cursor:
        cursor.execute(_AGENTS_TABLE_SQL)
        # Lightweight migrations for existing installations.
        cursor.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                WHERE table_name='agents' AND column_name='user_id') THEN
                    ALTER TABLE agents ADD COLUMN user_id VARCHAR(255);
                    CREATE INDEX IF NOT EXISTS idx_agents_user_id ON agents(user_id);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                WHERE table_name='agents' AND column_name='visibility') THEN
                    ALTER TABLE agents ADD COLUMN visibility VARCHAR(32) NOT NULL DEFAULT 'user';
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                WHERE table_name='agents' AND column_name='organization_id') THEN
                    ALTER TABLE agents ADD COLUMN organization_id UUID;
                    CREATE INDEX IF NOT EXISTS idx_agents_org_visibility ON agents(organization_id, visibility);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                WHERE table_name='agents' AND column_name='department_id') THEN
                    ALTER TABLE agents ADD COLUMN department_id UUID;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                WHERE table_name='agents' AND column_name='requires_plan_confirmation') THEN
                    ALTER TABLE agents ADD COLUMN requires_plan_confirmation BOOLEAN NOT NULL DEFAULT true;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                WHERE table_name='agents' AND column_name='skill_names') THEN
                    ALTER TABLE agents ADD COLUMN skill_names JSONB DEFAULT '[]';
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                WHERE table_name='agents' AND column_name='memory_enabled') THEN
                    ALTER TABLE agents ADD COLUMN memory_enabled BOOLEAN;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                WHERE table_name='agents' AND column_name='kind') THEN
                    ALTER TABLE agents ADD COLUMN kind VARCHAR(32) NOT NULL DEFAULT 'dedicated';
                END IF;
            END $$;
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_swarm_members (
                swarm_agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                dedicated_agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                position INT,
                created_at TIMESTAMPTZ DEFAULT now(),
                UNIQUE (swarm_agent_id, dedicated_agent_id)
            );
            CREATE INDEX IF NOT EXISTS idx_swarm_members_swarm_id ON agent_swarm_members(swarm_agent_id);
            CREATE INDEX IF NOT EXISTS idx_swarm_members_dedicated_id ON agent_swarm_members(dedicated_agent_id);
            """
        )
    conn.commit()
    logger.info("Agents table created or already exists.")


def _row_to_agent(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a DB row into a JSON-serialisable dict."""
    out: dict[str, Any] = {}
    for k, v in row.items():
        if v is None:
            out[k] = None
        elif isinstance(v, UUID):
            out[k] = str(v)
        elif hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif isinstance(v, (list, dict)) and not isinstance(v, (str, bytes)):
            out[k] = v
        else:
            out[k] = v
    return out


# Columns for list views — excludes large TEXT/JSONB prompt fields (detail endpoints load full rows).
_AGENT_LIST_COLUMNS = (
    "id, user_id, visibility, organization_id, department_id, "
    "name, description, opener, suggested_questions, "
    "knowledge_base_ids, tool_names, skill_names, workflow_ids, "
    "default_workflow_id, model_name, model_parameters, avatar, "
    "run_mode, kind, memory_enabled, requires_plan_confirmation, "
    "created_at, updated_at"
)

# Gallery / grid list only — detail fields come from GET /agents/{id}.
_AGENT_LIST_PAGE_COLUMNS = "id, user_id, name, description, model_name, kind, skill_names, tool_names, avatar, visibility"


def list_agents(
    conn,
    limit: int = 20,
    offset: int = 0,
    name_like: str | None = None,
    kind: str | None = None,
    user_id: str | None = None,
    organization_id: str | None = None,
    *,
    lightweight: bool = False,
    include_total: bool = False,
    list_page: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    """List agents with optional name filter and simple visibility scope.

    When *lightweight* is True, omit system_prompt, user_prompt_template, and
    prompt_variables from the SELECT (smaller payloads for paginated lists).

    When *list_page* is True, use a minimal column set for GET /agents list UI;
    callers should load full rows via get_agent when needed.

    When *include_total* is False (default), skip COUNT(*) and return *total* as
    ``offset + len(agents)`` (exact when this page is the last page; if
    ``len(agents) == limit`` there may be more rows). Pass *include_total=True*
    for COUNT(*) and full lightweight list rows (including swarm members).

    Returns (agents, total).
    """
    if list_page:
        select_sql = _AGENT_LIST_PAGE_COLUMNS
    elif lightweight:
        select_sql = _AGENT_LIST_COLUMNS
    else:
        select_sql = "*"
    with conn.cursor() as cursor:
        where = "WHERE 1=1"
        params: list[Any] = []
        if name_like and name_like.strip():
            where += " AND name ILIKE %s"
            params.append(f"%{name_like.strip()}%")
        if kind and kind.strip():
            where += " AND kind = %s"
            params.append(kind.strip())

        # Visibility scope:
        # - always include user's own agents (user_id match)
        # - include shared agents (visibility='org')
        if user_id:
            if organization_id:
                where += " AND (user_id = %s OR visibility = 'org')"
                params.append(user_id)
            else:
                where += " AND (user_id = %s OR visibility = 'org')"
                params.append(user_id)

        total: int
        if include_total:
            cursor.execute(f"SELECT COUNT(*) AS total FROM agents {where}", params)
            total = cursor.fetchone()["total"]

        params.extend([limit, offset])
        cursor.execute(
            f"""
            SELECT {select_sql} FROM agents
            {where}
            ORDER BY updated_at DESC
            LIMIT %s OFFSET %s
            """,
            params,
        )
        rows = cursor.fetchall()

    agents = [_row_to_agent(dict(r)) for r in rows]
    if lightweight or list_page:
        for a in agents:
            a.setdefault("system_prompt", None)
            a.setdefault("user_prompt_template", None)
            a.setdefault("prompt_variables", None)
    if list_page:
        for a in agents:
            a.setdefault("opener", None)
            a.setdefault("suggested_questions", None)
            a.setdefault("knowledge_base_ids", None)
            a.setdefault("workflow_ids", None)
            a.setdefault("default_workflow_id", None)
            a.setdefault("model_parameters", None)
            a.setdefault("run_mode", None)
            a.setdefault("memory_enabled", None)
            a.setdefault("requires_plan_confirmation", None)
            a.setdefault("organization_id", None)
            a.setdefault("department_id", None)
            a.setdefault("created_at", None)
            a.setdefault("updated_at", None)
    if not include_total:
        total = offset + len(agents)
    return agents, total


def get_agent(
    conn,
    agent_id: UUID,
    user_id: str | None = None,
    organization_id: str | None = None,
) -> dict[str, Any] | None:
    """Get a single agent by id (enforcing simple visibility rules)."""
    with conn.cursor() as cursor:
        if user_id and organization_id:
            cursor.execute(
                """
                SELECT * FROM agents
                WHERE id = %s AND (user_id = %s OR visibility='org')
                """,
                (agent_id, user_id),
            )
        elif user_id:
            cursor.execute(
                "SELECT * FROM agents WHERE id = %s AND (user_id = %s OR visibility = 'org')",
                (agent_id, user_id),
            )
        else:
            cursor.execute("SELECT * FROM agents WHERE id = %s", (agent_id,))
        row = cursor.fetchone()
    if not row:
        return None
    return _row_to_agent(dict(row))


def get_agent_by_name(
    conn,
    name: str,
    user_id: str | None = None,
    organization_id: str | None = None,
) -> dict[str, Any] | None:
    """Get the most recently updated agent by exact name."""
    with conn.cursor() as cursor:
        if user_id and organization_id:
            cursor.execute(
                """
                SELECT * FROM agents
                WHERE lower(name) = lower(%s)
                  AND (user_id = %s OR visibility='org')
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (name, user_id),
            )
        elif user_id:
            cursor.execute(
                """
                SELECT * FROM agents
                WHERE lower(name) = lower(%s) AND (user_id = %s OR visibility = 'org')
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (name, user_id),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM agents
                WHERE lower(name) = lower(%s)
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (name,),
            )
        row = cursor.fetchone()
    if not row:
        return None
    return _row_to_agent(dict(row))


def create_agent(
    conn,
    user_id: str | None,
    organization_id: str | None,
    department_id: str | None,
    name: str,
    description: str | None = None,
    system_prompt: str | None = None,
    user_prompt_template: str | None = None,
    prompt_variables: list[dict[str, Any]] | None = None,
    opener: str | None = None,
    suggested_questions: list[str] | None = None,
    knowledge_base_ids: list[str] | None = None,
    tool_names: list[str] | None = None,
    skill_names: list[str] | None = None,
    workflow_ids: list[str] | None = None,
    default_workflow_id: UUID | None = None,
    model_name: str | None = None,
    model_parameters: dict[str, Any] | None = None,
    avatar: str | None = None,
    run_mode: str | None = None,
    kind: str | None = None,
    memory_enabled: bool | None = None,
    requires_plan_confirmation: bool | None = None,
    visibility: str | None = None,
) -> UUID:
    """Create an agent and return its id."""
    agent_id = uuid4()
    prompt_vars = json.dumps(prompt_variables if prompt_variables is not None else [])
    suggested = json.dumps(suggested_questions if suggested_questions is not None else [])
    kb_ids = json.dumps(knowledge_base_ids if knowledge_base_ids is not None else [])
    tools = json.dumps(tool_names if tool_names is not None else [])
    skills = json.dumps(skill_names if skill_names is not None else [])
    wf_ids = json.dumps(workflow_ids if workflow_ids is not None else [])
    model_params = json.dumps(model_parameters) if model_parameters is not None else None

    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO agents (
                id, user_id, visibility, organization_id, department_id,
                name, description, system_prompt, user_prompt_template,
                prompt_variables, opener, suggested_questions, knowledge_base_ids,
                tool_names, skill_names, workflow_ids, default_workflow_id, model_name,
                model_parameters, avatar, run_mode, kind, memory_enabled, requires_plan_confirmation
            ) VALUES (
                %s, %s, %s, %s::uuid, %s::uuid,
                %s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb,
                %s, %s, %s::jsonb, %s, %s, %s, %s, %s
            )
            """,
            (
                agent_id,
                user_id,
                (visibility or "user"),
                organization_id,
                department_id,
                name,
                description,
                system_prompt,
                user_prompt_template,
                prompt_vars,
                opener,
                suggested,
                kb_ids,
                tools,
                skills,
                wf_ids,
                default_workflow_id,
                model_name,
                model_params,
                avatar,
                run_mode,
                (kind or "dedicated"),
                memory_enabled,
                True if requires_plan_confirmation is None else bool(requires_plan_confirmation),
            ),
        )
    return agent_id


def update_agent(
    conn,
    agent_id: UUID,
    user_id: str | None = None,
    name: str | None = None,
    description: str | None = None,
    system_prompt: str | None = None,
    user_prompt_template: str | None = None,
    prompt_variables: list[dict[str, Any]] | None = None,
    opener: str | None = None,
    suggested_questions: list[str] | None = None,
    knowledge_base_ids: list[str] | None = None,
    tool_names: list[str] | None = None,
    skill_names: list[str] | None = None,
    workflow_ids: list[str] | None = None,
    default_workflow_id: UUID | None = None,
    model_name: str | None = None,
    model_parameters: dict[str, Any] | None = None,
    avatar: str | None = None,
    run_mode: str | None = None,
    kind: str | None = None,
    memory_enabled: bool | None = None,
    requires_plan_confirmation: bool | None = None,
    visibility: str | None = None,
) -> bool:
    """Update an agent (only non-None fields). Returns whether any row was updated."""
    updates = ["updated_at = now()"]
    params: list[Any] = []

    if name is not None:
        updates.append("name = %s")
        params.append(name)
    if description is not None:
        updates.append("description = %s")
        params.append(description)
    if system_prompt is not None:
        updates.append("system_prompt = %s")
        params.append(system_prompt)
    if user_prompt_template is not None:
        updates.append("user_prompt_template = %s")
        params.append(user_prompt_template)
    if prompt_variables is not None:
        updates.append("prompt_variables = %s::jsonb")
        params.append(json.dumps(prompt_variables))
    if opener is not None:
        updates.append("opener = %s")
        params.append(opener)
    if suggested_questions is not None:
        updates.append("suggested_questions = %s::jsonb")
        params.append(json.dumps(suggested_questions))
    if knowledge_base_ids is not None:
        updates.append("knowledge_base_ids = %s::jsonb")
        params.append(json.dumps(knowledge_base_ids))
    if tool_names is not None:
        updates.append("tool_names = %s::jsonb")
        params.append(json.dumps(tool_names))
    if skill_names is not None:
        updates.append("skill_names = %s::jsonb")
        params.append(json.dumps(skill_names))
    if workflow_ids is not None:
        updates.append("workflow_ids = %s::jsonb")
        params.append(json.dumps(workflow_ids))
    if default_workflow_id is not None:
        updates.append("default_workflow_id = %s")
        params.append(default_workflow_id)
    if model_name is not None:
        updates.append("model_name = %s")
        params.append(model_name)
    if model_parameters is not None:
        updates.append("model_parameters = %s::jsonb")
        params.append(json.dumps(model_parameters))
    if avatar is not None:
        updates.append("avatar = %s")
        params.append(avatar)
    if run_mode is not None:
        updates.append("run_mode = %s")
        params.append(run_mode)
    if kind is not None:
        updates.append("kind = %s")
        params.append(kind)
    if memory_enabled is not None:
        updates.append("memory_enabled = %s")
        params.append(bool(memory_enabled))
    if requires_plan_confirmation is not None:
        updates.append("requires_plan_confirmation = %s")
        params.append(bool(requires_plan_confirmation))
    if visibility is not None:
        updates.append("visibility = %s")
        params.append(visibility)

    if len(params) == 0:
        return True

    params.append(agent_id)
    if user_id:
        params.append(user_id)
    with conn.cursor() as cursor:
        cursor.execute(
            f"UPDATE agents SET {', '.join(updates)} WHERE id = %s" + (" AND user_id = %s" if user_id else ""),
            params,
        )
        return cursor.rowcount > 0


def delete_agent(conn, agent_id: UUID, user_id: str | None = None) -> bool:
    """Delete an agent (optionally enforcing user_id). Returns whether any row was deleted."""
    with conn.cursor() as cursor:
        if user_id:
            cursor.execute("DELETE FROM agents WHERE id = %s AND user_id = %s", (agent_id, user_id))
        else:
            cursor.execute("DELETE FROM agents WHERE id = %s", (agent_id,))
        return cursor.rowcount > 0


def list_swarm_member_ids(conn, swarm_agent_id: UUID) -> list[str]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT dedicated_agent_id
            FROM agent_swarm_members
            WHERE swarm_agent_id = %s
            ORDER BY COALESCE(position, 2147483647), created_at, dedicated_agent_id
            """,
            (swarm_agent_id,),
        )
        rows = cursor.fetchall()
    return [str(r["dedicated_agent_id"]) for r in rows]


def list_swarm_members_bulk(conn, swarm_agent_ids: list[UUID]) -> dict[str, list[str]]:
    """Return mapping swarm_agent_id -> ordered dedicated_agent_id strings (one query)."""
    if not swarm_agent_ids:
        return {}
    uniq: list[UUID] = []
    seen: set[UUID] = set()
    for sid in swarm_agent_ids:
        if sid not in seen:
            seen.add(sid)
            uniq.append(sid)
    placeholders = ",".join(["%s"] * len(uniq))
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT swarm_agent_id, dedicated_agent_id
            FROM agent_swarm_members
            WHERE swarm_agent_id IN ({placeholders})
            ORDER BY swarm_agent_id, COALESCE(position, 2147483647), created_at, dedicated_agent_id
            """,
            uniq,
        )
        rows = cursor.fetchall()
    out: dict[str, list[str]] = {}
    for r in rows:
        sid = str(r["swarm_agent_id"])
        out.setdefault(sid, []).append(str(r["dedicated_agent_id"]))
    return out


def replace_swarm_members(conn, swarm_agent_id: UUID, dedicated_agent_ids: list[UUID]) -> None:
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM agent_swarm_members WHERE swarm_agent_id = %s", (swarm_agent_id,))
        for idx, dedicated_id in enumerate(dedicated_agent_ids):
            cursor.execute(
                """
                INSERT INTO agent_swarm_members (swarm_agent_id, dedicated_agent_id, position)
                VALUES (%s, %s, %s)
                ON CONFLICT (swarm_agent_id, dedicated_agent_id)
                DO UPDATE SET position = EXCLUDED.position
                """,
                (swarm_agent_id, dedicated_id, idx),
            )
