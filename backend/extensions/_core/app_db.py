"""Application database connection for user/auth/workflow/agent modules.

Uses PostgreSQL. Preferred source is config.yaml ``app_database.url``.
For unified single-DB deployment, falls back to ``database.postgres_url``.
Environment fallback: ``DEER_FLOW_APP_DATABASE_URL``.

Default DSN connections are served from a process-wide sync
:class:`psycopg_pool.ConnectionPool` (lazy-created). Callers keep using
``conn.close()`` in ``finally`` blocks; the pool is built with
``close_returns=True`` so ``close()`` returns the connection to the pool.

Explicit ``url=`` arguments bypass the pool and use a one-off
``psycopg.connect`` (scripts / migrations).
"""

from __future__ import annotations

import atexit
import logging
import os
import threading
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

logger = logging.getLogger(__name__)

_DEFAULT_URL = "postgresql://localhost:5432/deerflow"

_pool: ConnectionPool | None = None
_pool_dsn: str | None = None
_pool_lock = threading.Lock()


def get_app_database_url() -> str | None:
    """Return application database URL from config or environment."""
    try:
        from deerflow.config.app_config import get_app_config

        config = get_app_config()
        if config.app_database and config.app_database.url:
            return config.app_database.url
        database_cfg = getattr(config, "database", None)
        if database_cfg is not None and getattr(database_cfg, "backend", None) == "postgres":
            postgres_url = getattr(database_cfg, "postgres_url", "")
            if isinstance(postgres_url, str) and postgres_url.strip():
                return postgres_url
    except Exception:
        pass
    return None


def _normalize_dsn(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgres://", 1)
    return url


def _resolve_default_dsn() -> str:
    """Same resolution order as the historical ``get_app_db_connection()``."""
    db_url = get_app_database_url()
    if not db_url:
        db_url = os.environ.get("DEER_FLOW_APP_DATABASE_URL") or _DEFAULT_URL
    return _normalize_dsn(db_url)


def _pool_max_size() -> int:
    raw = os.environ.get("DEER_FLOW_APP_DB_POOL_MAX", "20")
    try:
        return max(1, min(int(raw), 256))
    except ValueError:
        return 20


def _get_or_create_pool() -> ConnectionPool:
    global _pool, _pool_dsn
    dsn = _resolve_default_dsn()
    with _pool_lock:
        if _pool is not None and not _pool.closed and _pool_dsn == dsn:
            return _pool
        if _pool is not None and not _pool.closed:
            try:
                _pool.close()
            except Exception:
                logger.exception("Error closing app DB pool before reconfigure")
        _pool_dsn = dsn
        _pool = ConnectionPool(
            conninfo=dsn,
            kwargs={"row_factory": dict_row},
            min_size=0,
            max_size=_pool_max_size(),
            open=True,
            close_returns=True,
            name="app_db",
        )
        return _pool


def close_app_db_pool() -> None:
    """Close the process-wide pool (idempotent). Safe when no pool exists."""
    global _pool, _pool_dsn
    with _pool_lock:
        if _pool is None:
            return
        try:
            if not _pool.closed:
                _pool.close()
        except Exception:
            logger.exception("Error closing app DB pool")
        finally:
            _pool = None
            _pool_dsn = None


atexit.register(close_app_db_pool)


def get_app_db_connection(url: str | None = None):
    """Get a synchronous PostgreSQL connection for the application database.

    Args:
        url: Override URL. If None, uses a connection from the process-wide pool
             for the resolved default DSN (config / env / default). If set,
             opens a standalone connection (not pooled); caller must ``close()``.

    Returns:
        psycopg.Connection with dict_row row factory.
    """
    if url is not None:
        db_url = _normalize_dsn(url)
        return psycopg.connect(db_url, row_factory=dict_row)
    pool = _get_or_create_pool()
    return pool.getconn()


def get_app_db_connection_optional() -> Any | None:
    """Return a connection if app database is configured, else None."""
    url = get_app_database_url() or os.environ.get("DEER_FLOW_APP_DATABASE_URL")
    if not url:
        return None
    return get_app_db_connection()
