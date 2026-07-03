"""Sa-Token remote validation (ContiNew Admin compatible)."""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from deerflow.config.app_config import SaTokenConfig

from starlette.requests import Request

logger = logging.getLogger(__name__)

_validate_cache: dict[str, tuple[float, SatokenIdentity]] = {}
_validate_cache_lock = threading.Lock()


@dataclass(frozen=True)
class SatokenIdentity:
    login_id: str
    username: str
    email: str | None
    real_name: str | None
    role_codes: tuple[str, ...]
    raw: dict[str, Any]


def normalize_authorization_value(raw: str, prefix: str = "Bearer") -> str:
    """Build a single Authorization header value without duplicate Bearer prefix."""
    value = (raw or "").strip()
    if not value:
        return ""
    pfx = (prefix or "Bearer").strip()
    if pfx and value.lower().startswith(pfx.lower() + " "):
        return value
    if pfx:
        return f"{pfx} {value}"
    return value


def looks_like_jwt(token: str) -> bool:
    """True when token has three non-empty dot-separated segments (HS256/JWT shape)."""
    parts = (token or "").split(".")
    return len(parts) == 3 and all(p.strip() for p in parts)


def _field_from_mapping(data: Mapping[str, Any], field: str) -> Any:
    if not field:
        return None
    if field in data:
        return data[field]
    parts = field.split(".")
    cur: Any = data
    for part in parts:
        if not isinstance(cur, Mapping) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _is_validate_success(body: Mapping[str, Any]) -> bool:
    """ContiNew Admin: success uses code 0 / \"0\" or success=true (not always HTTP 200 body code)."""
    if body.get("success") is True:
        return True
    code = body.get("code")
    if code is None:
        return True
    if code in (200, "200", 0, "0"):
        return True
    return False


def _normalize_username(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text.replace("@", "_") if text else ""


def pick_identity(payload: Mapping[str, Any], cfg: SaTokenConfig) -> tuple[str, str, str | None, str | None]:
    """Return (login_id, local_username, email, real_name) from validate response data."""
    login_id = _field_from_mapping(payload, cfg.login_id_field)
    username_val = _field_from_mapping(payload, cfg.username_field)
    email = _field_from_mapping(payload, cfg.email_field)
    real_name = _field_from_mapping(payload, cfg.real_name_field)

    login_str = str(login_id).strip() if login_id is not None else ""
    username_str = _normalize_username(username_val)

    if not login_str and username_str:
        login_str = username_str
    if not login_str:
        raise ValueError("Sa-Token response missing login id")

    local_username = username_str or login_str.replace("@", "_")
    email_str = (str(email).strip() if email else None) or None
    real_name_str = (str(real_name).strip() if real_name else None) or None
    return login_str, local_username, email_str, real_name_str


def pick_roles(payload: Mapping[str, Any], cfg: SaTokenConfig) -> list[str]:
    """Extract remote role codes from validate response data."""
    field = (cfg.roles_field or "").strip()
    if not field:
        return []
    raw = _field_from_mapping(payload, field)
    codes: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                code = item.strip()
                if code:
                    codes.append(code)
            elif isinstance(item, Mapping):
                for key in ("code", "roleCode", "name"):
                    val = item.get(key)
                    if val:
                        codes.append(str(val).strip())
                        break
    elif isinstance(raw, str) and raw.strip():
        codes.append(raw.strip())
    return codes


def _cache_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _get_cached_identity(token: str, ttl: int) -> SatokenIdentity | None:
    if ttl <= 0:
        return None
    key = _cache_key(token)
    with _validate_cache_lock:
        entry = _validate_cache.get(key)
        if entry is None:
            return None
        ts, identity = entry
        if time.monotonic() - ts >= ttl:
            _validate_cache.pop(key, None)
            return None
        return identity


def _set_cached_identity(token: str, identity: SatokenIdentity, ttl: int) -> None:
    if ttl <= 0:
        return
    key = _cache_key(token)
    with _validate_cache_lock:
        _validate_cache[key] = (time.monotonic(), identity)


def extract_token_from_request(
    request: Request,
    *,
    token_name: str = "Authorization",
) -> str | None:
    """Extract raw token from Authorization header, named header, or cookies."""
    header_name = (token_name or "Authorization").strip()
    auth = request.headers.get(header_name) or request.headers.get(header_name.lower())
    if auth:
        auth = auth.strip()
        if auth.lower().startswith("bearer "):
            return auth[7:].strip() or None
        return auth or None

    authorization = request.headers.get("authorization")
    if authorization:
        authorization = authorization.strip()
        if authorization.lower().startswith("bearer "):
            return authorization[7:].strip() or None
        return authorization or None

    for cookie_name in ("satoken", "access_token", "token"):
        cookie_val = request.cookies.get(cookie_name)
        if cookie_val:
            normalized = cookie_val.strip()
            if normalized.lower().startswith("bearer "):
                return normalized[7:].strip() or None
            return normalized or None

    return None


def build_validate_headers(token: str, cfg: SaTokenConfig, request: Request | None = None) -> dict[str, str]:
    """Headers for remote validate call."""
    header_name = cfg.token_name or "Authorization"
    headers = {header_name: normalize_authorization_value(token, cfg.token_prefix or "Bearer")}

    tenant_header = (cfg.tenant_header or "").strip()
    tenant_code = (cfg.tenant_code or "").strip()
    if request and tenant_header:
        from_request = request.headers.get(tenant_header)
        if from_request:
            headers[tenant_header] = from_request
    if tenant_header and tenant_code and tenant_header not in headers:
        headers[tenant_header] = tenant_code

    api_key = (cfg.validate_api_key or "").strip()
    if api_key:
        headers["X-Api-Key"] = api_key

    return headers


def _identity_from_validate_response(
    body: Mapping[str, Any],
    cfg: SaTokenConfig,
) -> SatokenIdentity | None:
    if not _is_validate_success(body):
        return None
    data = body.get("data")
    if not isinstance(data, Mapping):
        return None
    payload = dict(data)
    logger.debug("Sa-Token validate data: %s", payload)
    try:
        login_id, username, email, real_name = pick_identity(payload, cfg)
    except ValueError as e:
        logger.warning("Sa-Token identity parse error: %s", e)
        return None
    role_codes = tuple(pick_roles(payload, cfg))
    return SatokenIdentity(
        login_id=login_id,
        username=username,
        email=email,
        real_name=real_name,
        role_codes=role_codes,
        raw=payload,
    )


async def validate_satoken_token(
    token: str,
    cfg: SaTokenConfig,
    *,
    request: Request | None = None,
) -> SatokenIdentity | None:
    """Validate token via remote HTTP (default GET /auth/user/info)."""
    if not cfg.enabled or not (cfg.endpoint or "").strip():
        return None

    cached = _get_cached_identity(token, cfg.cache_ttl_seconds)
    if cached is not None:
        return cached

    endpoint = cfg.endpoint.rstrip("/")
    path = cfg.validate_path if cfg.validate_path.startswith("/") else f"/{cfg.validate_path}"
    url = f"{endpoint}{path}"
    headers = build_validate_headers(token, cfg, request)

    try:
        async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
            res = await client.get(url, headers=headers)
    except httpx.HTTPError as e:
        logger.warning("Sa-Token validate HTTP error: %s", e)
        return None

    if res.status_code == 401:
        return None
    if res.status_code != 200:
        logger.warning("Sa-Token validate unexpected status %s", res.status_code)
        return None

    try:
        body = res.json()
    except ValueError:
        logger.warning("Sa-Token validate non-JSON response")
        return None

    if not isinstance(body, Mapping):
        return None
    identity = _identity_from_validate_response(body, cfg)
    if identity is not None:
        _set_cached_identity(token, identity, cfg.cache_ttl_seconds)
    return identity


def validate_satoken_token_sync(
    token: str,
    cfg: SaTokenConfig,
    *,
    request: Request | None = None,
) -> SatokenIdentity | None:
    """Synchronous validate for use in sync auth dependencies."""
    if not cfg.enabled or not (cfg.endpoint or "").strip():
        return None

    cached = _get_cached_identity(token, cfg.cache_ttl_seconds)
    if cached is not None:
        return cached

    endpoint = cfg.endpoint.rstrip("/")
    path = cfg.validate_path if cfg.validate_path.startswith("/") else f"/{cfg.validate_path}"
    url = f"{endpoint}{path}"
    headers = build_validate_headers(token, cfg, request)

    try:
        with httpx.Client(timeout=cfg.timeout_seconds) as client:
            res = client.get(url, headers=headers)
    except httpx.HTTPError as e:
        logger.warning("Sa-Token validate HTTP error: %s", e)
        return None

    if res.status_code == 401:
        return None
    if res.status_code != 200:
        logger.warning("Sa-Token validate unexpected status %s", res.status_code)
        return None

    try:
        body = res.json()
    except ValueError:
        logger.warning("Sa-Token validate non-JSON response")
        return None

    if not isinstance(body, Mapping):
        return None
    identity = _identity_from_validate_response(body, cfg)
    if identity is not None:
        _set_cached_identity(token, identity, cfg.cache_ttl_seconds)
    return identity
