"""Tool run history: CRUD for tool_run_history table (app database)."""

import json
import logging
from typing import Any

from extensions._core.app_db import get_app_db_connection

logger = logging.getLogger(__name__)


def save_tool_run(tool_id: str, params: dict[str, Any], result: str) -> dict[str, Any]:
    """Save one tool run record. Returns the record with id, created_at."""
    conn = get_app_db_connection()
    try:
        params_str = json.dumps(params, ensure_ascii=False) if isinstance(params, dict) else "{}"
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tool_run_history (tool_id, params_json, result_json)
                VALUES (%s, %s::jsonb, %s)
                RETURNING id, tool_id, params_json, result_json, created_at
                """,
                (tool_id, params_str, result),
            )
            row = cur.fetchone()
        conn.commit()
        return _row_to_record(row)
    except Exception as e:
        logger.error("Error saving tool run: %s", e)
        raise
    finally:
        conn.close()


def list_tool_runs(
    tool_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List tool run records, optionally filtered by tool_id. Ordered by created_at DESC."""
    conn = get_app_db_connection()
    try:
        with conn.cursor() as cur:
            if tool_id:
                cur.execute(
                    """
                    SELECT id, tool_id, params_json, result_json, created_at
                    FROM tool_run_history
                    WHERE tool_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (tool_id, limit, offset),
                )
            else:
                cur.execute(
                    """
                    SELECT id, tool_id, params_json, result_json, created_at
                    FROM tool_run_history
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (limit, offset),
                )
            rows = cur.fetchall()
        return [_row_to_record(r) for r in rows]
    except Exception as e:
        logger.error("Error listing tool runs: %s", e)
        return []
    finally:
        conn.close()


def get_tool_run(record_id: str) -> dict[str, Any] | None:
    """Get a single record by id."""
    conn = get_app_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, tool_id, params_json, result_json, created_at
                FROM tool_run_history
                WHERE id = %s
                """,
                (str(record_id),),
            )
            row = cur.fetchone()
        return _row_to_record(row) if row else None
    except Exception as e:
        logger.warning("Error getting tool run %s: %s", record_id, e)
        return None
    finally:
        conn.close()


def delete_tool_run(record_id: str) -> bool:
    """Delete one record. Returns True if deleted."""
    conn = get_app_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tool_run_history WHERE id = %s", (str(record_id),))
            n = cur.rowcount
        conn.commit()
        return n > 0
    except Exception as e:
        logger.error("Error deleting tool run %s: %s", record_id, e)
        return False
    finally:
        conn.close()


def _row_to_record(row: dict) -> dict[str, Any]:
    out = {
        "id": str(row["id"]),
        "tool_id": row["tool_id"],
        "params_json": row["params_json"],
        "result_json": row["result_json"],
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
    }
    return out
