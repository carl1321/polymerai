"""Public share links for DB-backed agents: DDL and CRUD.

Tokens are stored as SHA-256 hex digests; the plaintext token is shown only once on publish/rotate.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)

_PUBLIC_LINKS_SQL = """
CREATE TABLE IF NOT EXISTS public_agent_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL UNIQUE,
    slug VARCHAR(64) NOT NULL UNIQUE,
    token_hash VARCHAR(128) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    expires_at TIMESTAMPTZ,
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_public_agent_links_slug ON public_agent_links(slug);
CREATE INDEX IF NOT EXISTS idx_public_agent_links_agent_id ON public_agent_links(agent_id);
"""

_PUBLIC_THREADS_SQL = """
CREATE TABLE IF NOT EXISTS public_agent_threads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    link_id UUID NOT NULL,
    thread_id VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (link_id) REFERENCES public_agent_links(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_public_agent_threads_link_id ON public_agent_threads(link_id);
"""


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_plain_token() -> str:
    return secrets.token_urlsafe(32)


def _new_slug() -> str:
    # URL-safe, no padding issues for path segments
    return secrets.token_urlsafe(12).replace("/", "_").replace("+", "-")


def init_public_agent_tables(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(_PUBLIC_LINKS_SQL)
        cur.execute(_PUBLIC_THREADS_SQL)
    conn.commit()
    logger.info("public_agent_links / public_agent_threads ready")


def get_link_by_slug(conn, slug: str) -> dict[str, Any] | None:
    init_public_agent_tables(conn)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, agent_id, slug, token_hash, enabled, expires_at, created_by, created_at, updated_at
            FROM public_agent_links WHERE slug = %s
            """,
            (slug,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def get_link_by_agent_id(conn, agent_id: UUID) -> dict[str, Any] | None:
    init_public_agent_tables(conn)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, agent_id, slug, token_hash, enabled, expires_at, created_by, created_at, updated_at
            FROM public_agent_links WHERE agent_id = %s
            """,
            (str(agent_id),),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def verify_link_token(link_row: dict[str, Any], plain_token: str) -> bool:
    if not plain_token or not link_row:
        return False
    try:
        import hmac

        return hmac.compare_digest(
            link_row["token_hash"],
            _hash_token(plain_token),
        )
    except Exception:
        return False


def is_link_active(link_row: dict[str, Any] | None) -> bool:
    if not link_row or not link_row.get("enabled"):
        return False
    exp = link_row.get("expires_at")
    if exp is None:
        return True
    now = datetime.now(timezone.utc)
    if isinstance(exp, datetime):
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return now < exp
    return True


def publish_or_update_link(
    conn,
    *,
    agent_id: UUID,
    user_id: UUID,
    expires_at: datetime | None = None,
) -> tuple[dict[str, Any], str]:
    """Create or replace publish link for agent. Returns (link_row_without_token, plain_token)."""
    init_public_agent_tables(conn)
    plain = _new_plain_token()
    th = _hash_token(plain)
    existing = get_link_by_agent_id(conn, agent_id)
    slug = existing["slug"] if existing else _new_slug()
    # Ensure slug unique when creating new
    if not existing:
        with conn.cursor() as cur:
            for _ in range(5):
                cur.execute("SELECT 1 FROM public_agent_links WHERE slug = %s", (slug,))
                if not cur.fetchone():
                    break
                slug = _new_slug()

    with conn.cursor() as cur:
        if existing:
            cur.execute(
                """
                UPDATE public_agent_links
                SET token_hash = %s, enabled = TRUE, expires_at = %s, updated_at = NOW(), created_by = %s
                WHERE agent_id = %s
                RETURNING id, agent_id, slug, token_hash, enabled, expires_at, created_by, created_at, updated_at
                """,
                (th, expires_at, str(user_id), str(agent_id)),
            )
        else:
            cur.execute(
                """
                INSERT INTO public_agent_links (id, agent_id, slug, token_hash, enabled, expires_at, created_by)
                VALUES (%s, %s, %s, %s, TRUE, %s, %s)
                RETURNING id, agent_id, slug, token_hash, enabled, expires_at, created_by, created_at, updated_at
                """,
                (str(uuid4()), str(agent_id), slug, th, expires_at, str(user_id)),
            )
        row = cur.fetchone()
    conn.commit()
    assert row
    return dict(row), plain


def rotate_token(
    conn,
    *,
    agent_id: UUID,
    user_id: UUID,
    expires_at: datetime | None = None,
) -> tuple[dict[str, Any], str]:
    init_public_agent_tables(conn)
    existing = get_link_by_agent_id(conn, agent_id)
    if not existing:
        raise ValueError("no_public_link")
    plain = _new_plain_token()
    th = _hash_token(plain)
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE public_agent_links
            SET token_hash = %s, expires_at = %s, updated_at = NOW(), created_by = %s
            WHERE agent_id = %s
            RETURNING id, agent_id, slug, token_hash, enabled, expires_at, created_by, created_at, updated_at
            """,
            (th, expires_at, str(user_id), str(agent_id)),
        )
        row = cur.fetchone()
    conn.commit()
    assert row
    return dict(row), plain


def set_enabled(conn, *, agent_id: UUID, enabled: bool) -> dict[str, Any] | None:
    init_public_agent_tables(conn)
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE public_agent_links SET enabled = %s, updated_at = NOW()
            WHERE agent_id = %s
            RETURNING id, agent_id, slug, token_hash, enabled, expires_at, created_by, created_at, updated_at
            """,
            (enabled, str(agent_id)),
        )
        row = cur.fetchone()
    conn.commit()
    return dict(row) if row else None


def get_thread_owner_link_id(conn, thread_id: str) -> UUID | None:
    init_public_agent_tables(conn)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT link_id FROM public_agent_threads WHERE thread_id = %s",
            (thread_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    raw = row["link_id"]
    return raw if isinstance(raw, UUID) else UUID(str(raw))


def bind_thread_to_link(conn, *, link_id: UUID, thread_id: str) -> None:
    """Associate a LangGraph thread with this public link; thread_id is globally unique."""
    init_public_agent_tables(conn)
    owner = get_thread_owner_link_id(conn, thread_id)
    if owner and owner != link_id:
        raise PermissionError("thread_bound_elsewhere")
    if owner == link_id:
        return
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public_agent_threads (id, link_id, thread_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (thread_id) DO NOTHING
            """,
            (str(uuid4()), str(link_id), thread_id),
        )
    conn.commit()
    # Re-check owner after insert (race)
    owner2 = get_thread_owner_link_id(conn, thread_id)
    if owner2 != link_id:
        raise PermissionError("thread_race")


def link_public_dict(link_row: dict[str, Any]) -> dict[str, Any]:
    """Strip token hash for API responses."""
    out = {k: v for k, v in link_row.items() if k != "token_hash"}
    for k, v in list(out.items()):
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif isinstance(v, UUID):
            out[k] = str(v)
    return out
