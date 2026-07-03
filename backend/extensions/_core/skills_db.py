from __future__ import annotations

import logging
import re
from typing import Any
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")

_SKILLS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS toolbox_skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL,
    description TEXT,
    laber_name TEXT,
    laber_description TEXT,
    visibility VARCHAR(32) NOT NULL DEFAULT 'user',
    user_id VARCHAR(255),
    organization_id UUID,
    group_name VARCHAR(255),
    skill_dir TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (organization_id, slug)
);
CREATE INDEX IF NOT EXISTS idx_toolbox_skills_user_id ON toolbox_skills(user_id);
CREATE INDEX IF NOT EXISTS idx_toolbox_skills_org_visibility ON toolbox_skills(organization_id, visibility);
CREATE INDEX IF NOT EXISTS idx_toolbox_skills_updated_at ON toolbox_skills(updated_at DESC);

CREATE TABLE IF NOT EXISTS agent_skill_bindings (
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    skill_id UUID NOT NULL REFERENCES toolbox_skills(id) ON DELETE CASCADE,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (agent_id, skill_id)
);
CREATE INDEX IF NOT EXISTS idx_agent_skill_bindings_agent ON agent_skill_bindings(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_skill_bindings_skill ON agent_skill_bindings(skill_id);
"""


def init_skills_tables(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(_SKILLS_TABLE_SQL)
        cur.execute("ALTER TABLE toolbox_skills ADD COLUMN IF NOT EXISTS laber_name TEXT")
        cur.execute("ALTER TABLE toolbox_skills ADD COLUMN IF NOT EXISTS laber_description TEXT")
    conn.commit()


def slugify_name(name: str) -> str:
    raw = (name or "").strip().lower()
    out = _SLUG_RE.sub("-", raw).strip("-")
    return out or "skill"


def _row_to_skill(row: dict[str, Any], agent_ids: list[str]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "slug": row["slug"],
        "description": row.get("description") or "",
        "laber_name": row.get("laber_name") or "",
        "laber_description": row.get("laber_description") or "",
        "visibility": row.get("visibility") or "user",
        "user_id": row.get("user_id"),
        "organization_id": str(row["organization_id"]) if row.get("organization_id") else None,
        "group_name": row.get("group_name"),
        "skill_dir": row.get("skill_dir"),
        "enabled": bool(row.get("enabled", True)),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
        "agent_ids": agent_ids,
    }


def _list_bindings(conn, skill_ids: list[UUID]) -> dict[UUID, list[str]]:
    if not skill_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT skill_id, agent_id
            FROM agent_skill_bindings
            WHERE skill_id = ANY(%s::uuid[])
            """,
            (skill_ids,),
        )
        rows = cur.fetchall()
    out: dict[UUID, list[str]] = {sid: [] for sid in skill_ids}
    for row in rows:
        sid = row["skill_id"]
        out.setdefault(sid, []).append(str(row["agent_id"]))
    return out


def list_visible_skills(
    conn,
    *,
    user_id: str,
    organization_id: str | None,
) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        if organization_id:
            cur.execute(
                """
                SELECT *
                FROM toolbox_skills
                WHERE user_id = %s
                   OR visibility = 'org'
                ORDER BY updated_at DESC
                """,
                (user_id,),
            )
        else:
            cur.execute(
                """
                SELECT *
                FROM toolbox_skills
                WHERE user_id = %s
                   OR visibility = 'org'
                ORDER BY updated_at DESC
                """,
                (user_id,),
            )
        rows = cur.fetchall()
    ids = [row["id"] for row in rows]
    bindings = _list_bindings(conn, ids)
    return [_row_to_skill(row, bindings.get(row["id"], [])) for row in rows]


def get_visible_skill(
    conn,
    *,
    skill_id: UUID,
    user_id: str,
    organization_id: str | None,
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        if organization_id:
            cur.execute(
                """
                SELECT *
                FROM toolbox_skills
                WHERE id = %s
                  AND (user_id = %s OR visibility = 'org')
                """,
                (skill_id, user_id),
            )
        else:
            cur.execute(
                """
                SELECT *
                FROM toolbox_skills
                WHERE id = %s AND (user_id = %s OR visibility = 'org')
                """,
                (skill_id, user_id),
            )
        row = cur.fetchone()
    if not row:
        return None
    bindings = _list_bindings(conn, [row["id"]])
    return _row_to_skill(row, bindings.get(row["id"], []))


def create_skill_metadata(
    conn,
    *,
    name: str,
    description: str,
    laber_name: str | None,
    laber_description: str | None,
    visibility: str,
    user_id: str,
    organization_id: str | None,
    group_name: str | None,
    skill_dir: str,
    enabled: bool = True,
) -> UUID:
    skill_id = uuid4()
    slug = slugify_name(name)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO toolbox_skills (
                id, name, slug, description, laber_name, laber_description, visibility, user_id, organization_id, group_name, skill_dir, enabled
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::uuid, %s, %s, %s)
            """,
            (
                skill_id,
                name,
                slug,
                description,
                laber_name,
                laber_description,
                visibility,
                user_id,
                organization_id,
                group_name,
                skill_dir,
                enabled,
            ),
        )
    conn.commit()
    return skill_id


def update_skill_metadata(
    conn,
    *,
    skill_id: UUID,
    visibility: str | None = None,
    group_name: str | None = None,
    enabled: bool | None = None,
) -> None:
    updates = ["updated_at = now()"]
    params: list[Any] = []
    if visibility is not None:
        updates.append("visibility = %s")
        params.append(visibility)
    if group_name is not None:
        updates.append("group_name = %s")
        params.append(group_name)
    if enabled is not None:
        updates.append("enabled = %s")
        params.append(bool(enabled))
    params.append(skill_id)
    with conn.cursor() as cur:
        cur.execute(f"UPDATE toolbox_skills SET {', '.join(updates)} WHERE id = %s", params)
    conn.commit()


def replace_skill_bindings(conn, *, skill_id: UUID, agent_ids: list[str], created_by: str) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM agent_skill_bindings WHERE skill_id = %s", (skill_id,))
        for raw in agent_ids:
            try:
                aid = UUID(str(raw))
            except Exception:
                continue
            cur.execute(
                """
                INSERT INTO agent_skill_bindings (agent_id, skill_id, created_by)
                VALUES (%s, %s, %s)
                ON CONFLICT (agent_id, skill_id) DO NOTHING
                """,
                (aid, skill_id, created_by),
            )
    conn.commit()
