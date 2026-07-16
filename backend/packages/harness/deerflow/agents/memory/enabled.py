from __future__ import annotations

import logging
import threading
import time
from uuid import UUID

from extensions._core.agents_db import get_agent as db_get_agent
from extensions._core.agents_db import get_agent_by_name
from extensions._core.app_db import get_app_db_connection

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 5.0
_cache_lock = threading.Lock()
_enabled_cache: dict[tuple[str | None, str | None], tuple[float, bool]] = {}


def _read_memory_enabled_from_db(agent_id: str | None, agent_name: str | None) -> bool | None:
    if not agent_id and not agent_name:
        return None

    conn = get_app_db_connection()
    try:
        row = None
        if agent_id:
            try:
                row = db_get_agent(conn, UUID(agent_id), user_id=None, organization_id=None)
            except (TypeError, ValueError):
                logger.warning("Invalid agent_id for memory toggle lookup: %r", agent_id)
        if row is None and agent_name:
            row = get_agent_by_name(conn, agent_name, user_id=None, organization_id=None)
        if row is None:
            return None
        value = row.get("memory_enabled")
        if value is None:
            return None
        return bool(value)
    except Exception:
        logger.exception("Failed to resolve memory_enabled from DB (agent_id=%r, agent_name=%r)", agent_id, agent_name)
        return None
    finally:
        conn.close()


def is_memory_enabled_for_agent(agent_id: str | None = None, agent_name: str | None = None) -> bool:
    key = (agent_id, agent_name)
    now = time.monotonic()
    with _cache_lock:
        cached = _enabled_cache.get(key)
        if cached and cached[0] > now:
            return cached[1]

    db_value = _read_memory_enabled_from_db(agent_id=agent_id, agent_name=agent_name)
    resolved = False if db_value is None else db_value

    with _cache_lock:
        _enabled_cache[key] = (now + _CACHE_TTL_SECONDS, resolved)
    return resolved


def clear_memory_enabled_cache() -> None:
    with _cache_lock:
        _enabled_cache.clear()
