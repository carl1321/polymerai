"""Public agent share: meta, publish (auth), and LangGraph reverse proxy."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from app.gateway.csrf_middleware import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, generate_csrf_token
from app.gateway.langgraph_auth import PUBLIC_LANGGRAPH_PROXY_SECRET_HEADER
from extensions._core.agents_db import get_agent as db_get_agent
from extensions._core.app_db import get_app_db_connection
from extensions._core.public_agent_links import (
    bind_thread_to_link,
    get_link_by_agent_id,
    get_link_by_slug,
    get_thread_owner_link_id,
    init_public_agent_tables,
    is_link_active,
    link_public_dict,
    publish_or_update_link,
    set_enabled,
    verify_link_token,
)
from extensions.auth.dependencies import CurrentUser, get_current_user
from extensions.public_agent.rate_limit import SlidingWindowLimiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/public", tags=["public-agent"])
security_bearer = HTTPBearer(auto_error=False)

_langgraph_base = os.getenv("LANGGRAPH_INTERNAL_URL", "http://127.0.0.1:2024").rstrip("/")
_PUBLIC_LANGGRAPH_SECRET = os.getenv("DEER_FLOW_PUBLIC_LANGGRAPH_PROXY_SECRET", "").strip()
_limiter = SlidingWindowLimiter(max_events=120, window_seconds=60.0)
DEFAULT_PUBLIC_TOKEN_TTL_DAYS = 1
MAX_PUBLIC_TOKEN_TTL_DAYS = 365

THREAD_SEGMENT_RE = re.compile(r"threads/([^/]+)")


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _extract_thread_ids(path: str) -> list[str]:
    return [m.group(1) for m in THREAD_SEGMENT_RE.finditer(path)]


def _public_path_forbidden(norm_path: str, method: str) -> str | None:
    """Return error detail if this LangGraph sub-path must be blocked for public links."""
    p = norm_path.lstrip("/")
    if method == "DELETE" and p.startswith("threads/"):
        return "thread_delete_blocked"
    if p.startswith("threads/search") or p.startswith("threads/count"):
        return "thread_search_blocked"
    if p.startswith("runs/") or p == "runs":
        return "stateless_runs_blocked"
    if "/copy" in p:
        return "thread_copy_blocked"
    if p.startswith("assistants") and method not in ("GET", "HEAD", "OPTIONS"):
        return "assistants_mutation_blocked"
    return None


def _patch_run_payload(data: dict[str, Any], agent_id: str) -> dict[str, Any]:
    ctx = data.get("context")
    if not isinstance(ctx, dict):
        ctx = {}
        data["context"] = ctx
    # LangGraph >=0.6 prefers context and rejects configurable+context.
    ctx["agent_id"] = agent_id
    ctx["deerflow_public_share"] = True
    return data


def _forward_headers(request: Request) -> dict[str, str]:
    out: dict[str, str] = {}
    skip = {
        "host",
        "content-length",
        "connection",
        "transfer-encoding",
        "accept-encoding",
    }
    for k, v in request.headers.items():
        if k.lower() in skip:
            continue
        out[k] = v
    return out


def _merge_csrf_into_cookie_header(cookie_value: str | None, csrf: str) -> str:
    parts: list[str] = []
    if cookie_value:
        for segment in cookie_value.split(";"):
            segment = segment.strip()
            if not segment:
                continue
            name = segment.split("=", 1)[0].strip()
            if name == CSRF_COOKIE_NAME:
                continue
            parts.append(segment)
    parts.append(f"{CSRF_COOKIE_NAME}={csrf}")
    return "; ".join(parts)


def _inject_upstream_csrf(headers: dict[str, str], method: str) -> None:
    """LangGraph Server enforces CSRF on mutating methods; inject a matching pair for proxied public traffic."""
    if method.upper() not in ("POST", "PUT", "PATCH", "DELETE"):
        return
    csrf = generate_csrf_token()
    cookie_key = next((k for k in headers if k.lower() == "cookie"), None)
    if cookie_key:
        headers[cookie_key] = _merge_csrf_into_cookie_header(headers[cookie_key], csrf)
    else:
        headers["Cookie"] = f"{CSRF_COOKIE_NAME}={csrf}"
    headers[CSRF_HEADER_NAME] = csrf


class PublishBody(BaseModel):
    expires_at: datetime | None = Field(default=None, description="Optional UTC expiry")
    expires_in_days: int | None = Field(
        default=None,
        ge=1,
        le=MAX_PUBLIC_TOKEN_TTL_DAYS,
        description="TTL in days. If provided, overrides expires_at.",
    )


class PublishResponse(BaseModel):
    slug: str
    token: str
    url_path: str
    expires_at: datetime | None = None


def _parse_public_token(request: Request, credentials: HTTPAuthorizationCredentials | None) -> str | None:
    if credentials and credentials.scheme.lower() == "bearer" and credentials.credentials:
        return credentials.credentials
    q = request.query_params.get("token")
    return q or None


@router.get("/p/{slug}/meta")
async def public_meta(
    slug: str,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security_bearer),
) -> dict[str, Any]:
    token = _parse_public_token(request, credentials)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing_token")

    conn = get_app_db_connection()
    try:
        init_public_agent_tables(conn)
        row = get_link_by_slug(conn, slug)
        if not row or not verify_link_token(row, token):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "invalid_link")
        if not is_link_active(row):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "link_disabled_or_expired")

        aid = row["agent_id"]
        if isinstance(aid, UUID):
            aid_str = str(aid)
        else:
            aid_str = str(aid)

        agent = db_get_agent(conn, UUID(aid_str), user_id=None, organization_id=None)
        if not agent:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "agent_not_found")

        return {
            "valid": True,
            "slug": row["slug"],
            "agent_id": aid_str,
            "agent_name": agent.get("name") or "Agent",
            "description": agent.get("description") or "",
            "expires_at": row.get("expires_at").isoformat() if row.get("expires_at") else None,
        }
    finally:
        conn.close()


@router.post("/agents/{agent_id}/publish", response_model=PublishResponse)
async def publish_agent(
    agent_id: str,
    body: PublishBody | None = None,
    current_user: CurrentUser = Depends(get_current_user),
) -> PublishResponse:
    try:
        uid = UUID(agent_id)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_agent_id")

    conn = get_app_db_connection()
    try:
        agent = db_get_agent(
            conn,
            uid,
            user_id=str(current_user.id),
            organization_id=str(current_user.organization_id) if current_user.organization_id else None,
        )
        if not agent:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "agent_not_found")

        exp = body.expires_at if body else None
        if body and body.expires_in_days is not None:
            exp = datetime.now(UTC) + timedelta(days=body.expires_in_days)
        elif exp is None:
            exp = datetime.now(UTC) + timedelta(days=DEFAULT_PUBLIC_TOKEN_TTL_DAYS)
        if exp and exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)

        row, plain = publish_or_update_link(
            conn,
            agent_id=uid,
            user_id=current_user.id,
            expires_at=exp,
        )
        slug = row["slug"]
        return PublishResponse(
            slug=slug,
            token=plain,
            url_path=f"/a/{slug}?token={plain}",
            expires_at=row.get("expires_at"),
        )
    finally:
        conn.close()


@router.post("/agents/{agent_id}/disable")
async def disable_public_link(
    agent_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        uid = UUID(agent_id)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_agent_id")
    conn = get_app_db_connection()
    try:
        agent = db_get_agent(
            conn,
            uid,
            user_id=str(current_user.id),
            organization_id=str(current_user.organization_id) if current_user.organization_id else None,
        )
        if not agent:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "agent_not_found")
        row = set_enabled(conn, agent_id=uid, enabled=False)
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no_public_link")
        return {"ok": True, "link": link_public_dict(row)}
    finally:
        conn.close()


@router.post("/agents/{agent_id}/rotate-token", response_model=PublishResponse)
async def rotate_public_token(
    agent_id: str,
    body: PublishBody | None = None,
    current_user: CurrentUser = Depends(get_current_user),
) -> PublishResponse:
    try:
        uid = UUID(agent_id)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_agent_id")
    conn = get_app_db_connection()
    try:
        agent = db_get_agent(
            conn,
            uid,
            user_id=str(current_user.id),
            organization_id=str(current_user.organization_id) if current_user.organization_id else None,
        )
        if not agent:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "agent_not_found")
        try:
            rotate_exp = None
            if body and body.expires_in_days is not None:
                rotate_exp = datetime.now(UTC) + timedelta(days=body.expires_in_days)
            elif body and body.expires_at is not None:
                rotate_exp = body.expires_at
            else:
                rotate_exp = datetime.now(UTC) + timedelta(days=DEFAULT_PUBLIC_TOKEN_TTL_DAYS)
            if rotate_exp and rotate_exp.tzinfo is None:
                rotate_exp = rotate_exp.replace(tzinfo=UTC)
            # Reuse publish path to guarantee token + expiry + enabled state are all refreshed together.
            row, plain = publish_or_update_link(
                conn,
                agent_id=uid,
                user_id=current_user.id,
                expires_at=rotate_exp,
            )
        except ValueError:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no_public_link")
        slug = row["slug"]
        return PublishResponse(
            slug=slug,
            token=plain,
            url_path=f"/a/{slug}?token={plain}",
            expires_at=row.get("expires_at"),
        )
    finally:
        conn.close()


@router.get("/agents/{agent_id}/link")
async def get_public_link_status(
    agent_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        uid = UUID(agent_id)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_agent_id")
    conn = get_app_db_connection()
    try:
        agent = db_get_agent(
            conn,
            uid,
            user_id=str(current_user.id),
            organization_id=str(current_user.organization_id) if current_user.organization_id else None,
        )
        if not agent:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "agent_not_found")
        row = get_link_by_agent_id(conn, uid)
        if not row:
            return {"published": False}
        active = is_link_active(row)
        return {
            # "published" should reflect whether the link is currently usable,
            # not merely whether a historical DB record exists.
            "published": active,
            "active": active,
            "has_record": True,
            "link": link_public_dict(row),
        }
    finally:
        conn.close()


@router.api_route(
    "/p/{slug}/lg/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def proxy_langgraph(
    slug: str,
    path: str,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security_bearer),
) -> StreamingResponse:
    token = _parse_public_token(request, credentials)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing_token")

    ip = _client_ip(request)
    if not _limiter.check(f"{ip}:{slug}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate_limited")

    conn = get_app_db_connection()
    link_row: dict[str, Any] | None = None
    try:
        init_public_agent_tables(conn)
        link_row = get_link_by_slug(conn, slug)
        if not link_row or not verify_link_token(link_row, token):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid_token")
        if not is_link_active(link_row):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "link_disabled_or_expired")

        link_id = link_row["id"]
        if not isinstance(link_id, UUID):
            link_id = UUID(str(link_id))

        agent_id_str = str(link_row["agent_id"])

        norm_path = path or ""
        if norm_path.startswith("/"):
            norm_path = norm_path[1:]

        block = _public_path_forbidden(norm_path, request.method)
        if block:
            logger.warning("public proxy blocked path=%s reason=%s", norm_path, block)
            raise HTTPException(status.HTTP_403_FORBIDDEN, block)

        for tid in _extract_thread_ids(norm_path):
            if tid in ("search", "count"):
                continue
            owner = get_thread_owner_link_id(conn, tid)
            if owner is None:
                try:
                    bind_thread_to_link(conn, link_id=link_id, thread_id=tid)
                except PermissionError:
                    raise HTTPException(status.HTTP_403_FORBIDDEN, "thread_forbidden")
            elif owner != link_id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "thread_forbidden")

        body = await request.body()
        content: bytes = body
        ct = request.headers.get("content-type", "")
        if request.method == "POST" and body and "application/json" in ct.lower():
            try:
                data = json.loads(body.decode("utf-8"))
                if isinstance(data, dict):
                    data = _patch_run_payload(data, agent_id_str)
                    content = json.dumps(data).encode("utf-8")
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

        url = f"{_langgraph_base}/{norm_path}" if norm_path else _langgraph_base
        params = list(request.query_params.multi_items())

        headers = _forward_headers(request)
        _inject_upstream_csrf(headers, request.method)
        if _PUBLIC_LANGGRAPH_SECRET:
            headers[PUBLIC_LANGGRAPH_PROXY_SECRET_HEADER] = _PUBLIC_LANGGRAPH_SECRET
        timeout = httpx.Timeout(600.0, connect=30.0)

        # Keep AsyncClient open until the response body is fully streamed (do not close before aiter_bytes finishes).
        hc = httpx.AsyncClient(timeout=timeout)
        try:
            req = hc.build_request(
                request.method,
                url,
                headers=headers,
                content=content if content else None,
                params=params or None,
            )
            resp = await hc.send(req, stream=True)
        except Exception:
            await hc.aclose()
            raise

        hop_skip = {
            "connection",
            "transfer-encoding",
            "content-encoding",
            "keep-alive",
        }
        out_headers = {k: v for k, v in resp.headers.items() if k.lower() not in hop_skip}

        async def body_iter():
            try:
                async for chunk in resp.aiter_bytes():
                    yield chunk
            finally:
                await resp.aclose()
                await hc.aclose()

        return StreamingResponse(
            body_iter(),
            status_code=resp.status_code,
            headers=out_headers,
        )
    finally:
        conn.close()
