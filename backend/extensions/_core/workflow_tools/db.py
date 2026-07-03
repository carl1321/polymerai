from __future__ import annotations

import json
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_SCRIPT_TEMPLATE = '''from langchain_core.tools import tool


@tool
def {tool_name}(query: str) -> str:
    """{description}"""
    return f"ok: {{query}}"
'''


def init_workflow_tools_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_tools (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(128) NOT NULL UNIQUE,
                display_name VARCHAR(255) NOT NULL,
                description TEXT DEFAULT '',
                source VARCHAR(32) NOT NULL DEFAULT 'script',
                source_ref VARCHAR(255),
                script TEXT,
                requirements TEXT DEFAULT '',
                status VARCHAR(32) NOT NULL DEFAULT 'draft',
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                last_test_ok BOOLEAN NOT NULL DEFAULT FALSE,
                cached_schema JSONB,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_workflow_tools_status ON workflow_tools(status);
            CREATE INDEX IF NOT EXISTS idx_workflow_tools_source ON workflow_tools(source);
            CREATE INDEX IF NOT EXISTS idx_workflow_tools_enabled ON workflow_tools(enabled);
            """
        )
    logger.info("workflow_tools table ready.")


def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    if out.get("cached_schema") is not None and not isinstance(out["cached_schema"], dict):
        try:
            out["cached_schema"] = json.loads(out["cached_schema"])
        except Exception:
            pass
    return out


def list_tools(
    conn,
    *,
    status: str | None = None,
    source: str | None = None,
    published_only: bool = False,
    catalog_only: bool = False,
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: list[Any] = []
    if status:
        clauses.append("status = %s")
        params.append(status)
    if source:
        clauses.append("source = %s")
        params.append(source)
    if published_only:
        clauses.append("(status = 'published')")
    if catalog_only:
        clauses.append(
            "((source = 'script' AND status = 'published') OR (source IN ('builtin', 'mcp') AND enabled = TRUE AND status = 'published'))"
        )
    sql = f"SELECT * FROM workflow_tools WHERE {' AND '.join(clauses)} ORDER BY display_name ASC"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [_row_to_dict(r) for r in rows]


def get_tool_by_id(conn, tool_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM workflow_tools WHERE id = %s", (tool_id,))
        row = cur.fetchone()
    return _row_to_dict(row) if row else None


def delete_tool(conn, tool_id: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM workflow_tools WHERE id = %s", (tool_id,))
        deleted = cur.rowcount > 0
    conn.commit()
    return deleted


def get_tool_by_name(conn, name: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM workflow_tools WHERE name = %s", (name,))
        row = cur.fetchone()
    return _row_to_dict(row) if row else None


def create_script_tool(
    conn,
    *,
    name: str,
    display_name: str,
    description: str = "",
) -> dict[str, Any]:
    tool_id = str(uuid.uuid4())
    script = DEFAULT_SCRIPT_TEMPLATE.format(tool_name=name, description=description or display_name)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO workflow_tools (
                id, name, display_name, description, source, script, status, enabled
            ) VALUES (%s, %s, %s, %s, 'script', %s, 'draft', TRUE)
            RETURNING *
            """,
            (tool_id, name, display_name, description, script),
        )
        row = cur.fetchone()
    conn.commit()
    return _row_to_dict(row)


def update_tool(conn, tool_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    allowed = {
        "display_name",
        "description",
        "script",
        "requirements",
        "cached_schema",
        "last_test_ok",
        "status",
        "enabled",
    }
    sets: list[str] = []
    params: list[Any] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key == "cached_schema" and value is not None:
            sets.append(f"{key} = %s::jsonb")
            params.append(json.dumps(value, ensure_ascii=False))
        else:
            sets.append(f"{key} = %s")
            params.append(value)
    if not sets:
        return get_tool_by_id(conn, tool_id)
    sets.append("updated_at = NOW()")
    params.append(tool_id)
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE workflow_tools SET {', '.join(sets)} WHERE id = %s RETURNING *",
            params,
        )
        row = cur.fetchone()
    conn.commit()
    return _row_to_dict(row) if row else None


def upsert_system_tool(
    conn,
    *,
    name: str,
    display_name: str,
    description: str,
    source: str,
    source_ref: str,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO workflow_tools (
                id, name, display_name, description, source, source_ref,
                status, enabled, last_test_ok
            ) VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, 'published', FALSE, FALSE)
            ON CONFLICT (name) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                description = EXCLUDED.description,
                source = EXCLUDED.source,
                source_ref = EXCLUDED.source_ref,
                updated_at = NOW()
            """,
            (name, display_name, description, source, source_ref),
        )
    conn.commit()
