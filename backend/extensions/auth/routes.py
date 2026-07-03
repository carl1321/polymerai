"""Auth API routes: public-key, login, logout, me, refresh."""

import logging
from datetime import datetime
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from deerflow.config.app_config import get_app_config
from extensions._core.ragflow_user_key import ensure_user_ragflow_key
from extensions.auth.casdoor import (
    build_authorize_url,
    exchange_code_for_tokens,
    get_account,
    new_state,
    pick_identity,
    verify_casdoor_jwt,
)
from extensions.auth.crypto import CRYPTO_AVAILABLE, decrypt_password, get_public_key
from extensions.auth.db import TokenBlacklist, UserDB
from extensions.auth.dependencies import CurrentUser, get_current_user
from extensions.auth.jwt import create_access_token, decode_token, get_token_jti
from extensions.auth.models import LoginRequest, LoginResponse, TokenResponse, UserInfoResponse
from extensions.auth.password import verify_password
from extensions.auth.user_provision import find_or_create_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer()

_CASDOOR_STATE_COOKIE = "deerflow_casdoor_state"


def _normalize_email(email: str | None, username: str) -> str:
    """Normalize email for API response."""
    e = (email or "").strip()
    if not e or " " in e or e.lower().endswith(".local"):
        return f"{(username or 'user').replace('@', '_')}@example.com"
    parts = e.split("@")
    if len(parts) != 2 or not parts[0] or "." not in parts[1]:
        return f"{(username or 'user').replace('@', '_')}@example.com"
    return e


def _serialize_role(role: dict) -> dict:
    out = {}
    for k, v in role.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif isinstance(v, UUID):
            out[k] = str(v)
        else:
            out[k] = v
    return out


@router.get("/public-key")
async def get_public_key_endpoint() -> dict:
    """Return RSA public key for client-side password encryption."""
    if not CRYPTO_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password encryption not available. Install pycryptodome.",
        )
    try:
        public_key = get_public_key()
        return {"public_key": public_key, "algorithm": "RSA", "key_size": 2048}
    except Exception as e:
        logger.error("Error getting public key: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve public key")


@router.get("/casdoor/enabled")
async def casdoor_enabled() -> dict:
    """Expose whether Casdoor login is enabled (for frontend UI branching)."""
    cfg = get_app_config()
    cd = cfg.auth.casdoor
    if not cd.enabled:
        return {"enabled": False}
    return {"enabled": True}


@router.get("/satoken/enabled")
async def satoken_enabled() -> dict:
    """Expose whether Sa-Token validation is enabled (for frontend UI branching)."""
    cfg = get_app_config()
    st = cfg.auth.satoken
    if not st.enabled:
        return {"enabled": False, "allow_local_login": True}
    return {"enabled": True, "allow_local_login": st.allow_local_login}


def _get_forwarded(req: Request, name: str) -> str | None:
    v = req.headers.get(name)
    if not v:
        return None
    # Some proxies provide comma-separated values; first one is the original.
    return v.split(",")[0].strip() or None


def _get_external_base_url(req: Request) -> str:
    """Best-effort external base URL behind reverse proxies."""
    proto = _get_forwarded(req, "x-forwarded-proto") or req.url.scheme
    host = _get_forwarded(req, "x-forwarded-host") or req.headers.get("host") or req.url.netloc
    host = (host or "").split(",")[0].strip()

    # If host already contains port (host:port), keep it.
    if ":" in host and not host.endswith("]"):  # IPv6 without port endswith ]
        return f"{proto}://{host}"

    forwarded_port = _get_forwarded(req, "x-forwarded-port")
    if forwarded_port and forwarded_port.isdigit():
        port = int(forwarded_port)
        default_port = 443 if proto == "https" else 80
        if port != default_port:
            return f"{proto}://{host}:{port}"

    return f"{proto}://{host}"


def _request_is_https(req: Request) -> bool:
    proto = (_get_forwarded(req, "x-forwarded-proto") or req.url.scheme or "").lower()
    return proto == "https"


def _casdoor_state_cookie_params(req: Request) -> dict:
    cfg = get_app_config().auth.casdoor
    out: dict = {
        "path": "/",
        "httponly": True,
        "samesite": "lax",
        "secure": _request_is_https(req),
    }
    dom = (cfg.state_cookie_domain or "").strip()
    if dom:
        out["domain"] = dom
    return out


def _get_casdoor_redirect_uri(req: Request) -> str:
    cfg = get_app_config()
    if cfg.auth.casdoor.redirect_uri:
        return cfg.auth.casdoor.redirect_uri
    # Infer from request/proxy headers.
    base = _get_external_base_url(req)
    return f"{base}/api/auth/casdoor/callback"


@router.get("/casdoor/login")
async def casdoor_login(req: Request, resp: Response) -> Response:
    """Start Casdoor OAuth2/OIDC login by redirecting to Casdoor authorize URL."""
    cfg = get_app_config().auth.casdoor
    if not cfg.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Casdoor login is disabled")
    if not (cfg.endpoint and cfg.client_id and cfg.client_secret):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Casdoor config incomplete")

    redirect_uri = _get_casdoor_redirect_uri(req)
    state = new_state()
    authorize_url = build_authorize_url(
        endpoint=cfg.endpoint,
        client_id=cfg.client_id,
        redirect_uri=redirect_uri,
        state=state,
    )

    # Store state in short-lived cookie to prevent CSRF.
    resp = Response(status_code=status.HTTP_302_FOUND)
    resp.headers["Location"] = authorize_url
    ck = _casdoor_state_cookie_params(req)
    resp.set_cookie(_CASDOOR_STATE_COOKIE, state, max_age=300, **ck)
    return resp


@router.get("/casdoor/callback", name="casdoor_callback")
async def casdoor_callback(req: Request) -> Response:
    """Casdoor callback: exchange code, get-account, map user; redirect with Casdoor JWT."""
    cfg = get_app_config().auth.casdoor
    if not cfg.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Casdoor login is disabled")

    params = dict(req.query_params)
    code = params.get("code")
    state = params.get("state")
    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing code")

    cookie_state = req.cookies.get(_CASDOOR_STATE_COOKIE)
    if not cookie_state or not state or cookie_state != state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state")

    redirect_uri = _get_casdoor_redirect_uri(req)
    token_result = await exchange_code_for_tokens(
        endpoint=cfg.endpoint or "",
        client_id=cfg.client_id or "",
        client_secret=cfg.client_secret or "",
        redirect_uri=redirect_uri,
        code=code,
        certificate_pem=cfg.certificate,
    )
    if not token_result.access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access_token from Casdoor")

    try:
        casdoor_user = await get_account(
            endpoint=cfg.endpoint or "",
            access_token=token_result.access_token,
            certificate_pem=cfg.certificate,
        )
    except Exception as e:
        logger.error("Failed to get Casdoor account: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Failed to get user from Casdoor")

    username, email, real_name = pick_identity(casdoor_user)
    user = find_or_create_user(
        username=username,
        email=email,
        real_name=real_name,
        auto_create=cfg.auto_create_user,
    )
    if not user:
        # When auto-create is enabled, provisioning failures are usually DB/constraint issues.
        status_code = status.HTTP_403_FORBIDDEN if not cfg.auto_create_user else status.HTTP_500_INTERNAL_SERVER_ERROR
        detail = "User is not provisioned" if not cfg.auto_create_user else "Failed to provision user"
        raise HTTPException(status_code=status_code, detail=detail)

    raw_id = user["id"]
    user_id = raw_id if isinstance(raw_id, UUID) else UUID(str(raw_id))
    ensure_user_ragflow_key(dict(user), user.get("username") or username)
    UserDB.update_last_login(user_id)

    bearer = token_result.id_token
    if not bearer:
        # Some Casdoor setups may not return id_token; allow JWT access_token if it looks like a JWT.
        access_token = token_result.access_token
        if access_token and access_token.count(".") == 2:
            bearer = access_token
    if not bearer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Casdoor JWT (id_token or JWT access_token)",
        )
    if not verify_casdoor_jwt(bearer, cfg):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Casdoor JWT",
        )

    # Redirect back to frontend login page with token in query.
    # The frontend will consume it and store in localStorage.
    frontend_login = "/login"
    location = f"{frontend_login}?{urlencode({'token': bearer})}"
    resp = Response(status_code=status.HTTP_302_FOUND)
    resp.headers["Location"] = location
    resp.delete_cookie(_CASDOOR_STATE_COOKIE, **_casdoor_state_cookie_params(req))
    return resp


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    """Login with username and password; returns JWT and user info."""
    st = get_app_config().auth.satoken
    if st.enabled and not st.allow_local_login:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local login is disabled. Use your organization SSO.",
        )
    user_data = UserDB.get_by_username(request.username)
    if not user_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    if not user_data.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled")

    password = request.password
    if len(password) > 100 and all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=" for c in password):
        decrypted = decrypt_password(password)
        if decrypted is not None:
            password = decrypted
        else:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    password_hash = user_data.get("password_hash")
    if not password_hash or not verify_password(password, password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    raw_id = user_data["id"]
    user_id = raw_id if isinstance(raw_id, UUID) else UUID(str(raw_id))
    ensure_user_ragflow_key(dict(user_data), request.username)
    roles = UserDB.get_user_roles(user_id)
    permissions = UserDB.get_user_permissions(user_id)

    token = create_access_token(
        user_id=str(user_id),
        username=user_data["username"],
        is_superuser=user_data.get("is_superuser", False),
    )
    UserDB.update_last_login(user_id)

    user_response = {
        "id": str(user_id),
        "username": user_data["username"],
        "email": _normalize_email(user_data.get("email"), user_data["username"]),
        "real_name": user_data.get("real_name"),
        "is_superuser": user_data.get("is_superuser", False),
        "roles": [_serialize_role(r) for r in roles],
        "permissions": permissions,
        "organization_id": str(user_data["organization_id"]) if user_data.get("organization_id") else None,
        "department_id": str(user_data["department_id"]) if user_data.get("department_id") else None,
        "data_permission_level": user_data.get("data_permission_level", "self"),
        "is_active": user_data.get("is_active", True),
        "last_login_at": user_data.get("last_login_at").isoformat() if user_data.get("last_login_at") else None,
        "created_at": user_data.get("created_at").isoformat() if user_data.get("created_at") else None,
        "updated_at": user_data.get("updated_at").isoformat() if user_data.get("updated_at") else None,
    }
    return LoginResponse(access_token=token, token_type="bearer", user=user_response)


@router.post("/logout")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Logout: blacklist DeerFlow JWT; Casdoor Bearer is accepted for no-op logout (client clears storage)."""
    token = credentials.credentials
    payload = decode_token(token)
    if payload:
        token_jti = get_token_jti(token)
        user_id_str = payload.get("sub")
        expires_at = datetime.fromtimestamp(payload.get("exp", 0))
        if token_jti and user_id_str:
            try:
                TokenBlacklist.add_token(token_jti, UUID(user_id_str), expires_at)
            except Exception as e:
                logger.error("Error adding token to blacklist: %s", e)
        return {"message": "Logged out successfully"}
    cfg = get_app_config()
    cd = cfg.auth.casdoor
    if cd.enabled and verify_casdoor_jwt(token, cd):
        return {"message": "Logged out successfully"}
    st = cfg.auth.satoken
    if st.enabled:
        from extensions.auth.satoken import validate_satoken_token_sync

        if validate_satoken_token_sync(token, st) is not None:
            return {"message": "Logged out successfully"}
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


@router.get("/me", response_model=UserInfoResponse)
async def get_current_user_info(current_user: CurrentUser = Depends(get_current_user)) -> UserInfoResponse:
    """Return current user info (roles, permissions; menus empty in step 1)."""
    user_data = UserDB.get_by_id(current_user.id)
    if not user_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    ensure_user_ragflow_key(dict(user_data), current_user.username)
    roles_data = UserDB.get_user_roles(current_user.id)
    permissions = UserDB.get_user_permissions(current_user.id)

    roles_out = [
        {
            "id": str(r["id"]) if isinstance(r.get("id"), UUID) else r.get("id"),
            "code": r.get("code", ""),
            "name": r.get("name", ""),
            "description": r.get("description"),
            "is_system": r.get("is_system", False),
            "is_active": r.get("is_active", True),
            "sort_order": r.get("sort_order", 0),
            "created_at": r.get("created_at").isoformat() if hasattr(r.get("created_at"), "isoformat") else r.get("created_at"),
            "updated_at": r.get("updated_at").isoformat() if hasattr(r.get("updated_at"), "isoformat") else r.get("updated_at"),
        }
        for r in roles_data
    ]

    return UserInfoResponse(
        id=current_user.id,
        username=current_user.username,
        email=_normalize_email(user_data.get("email"), current_user.username),
        real_name=current_user.real_name,
        is_superuser=current_user.is_superuser,
        roles=roles_out,
        permissions=permissions,
        menus=[],
        organization=None,
        department=None,
        data_permission_level=current_user.data_permission_level,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(credentials: HTTPAuthorizationCredentials = Depends(security), current_user: CurrentUser = Depends(get_current_user)) -> TokenResponse:
    token = credentials.credentials
    cd = get_app_config().auth.casdoor
    # HS256 DeerFlow JWT: allow refresh.
    # RS256 Casdoor JWT: reject refresh to keep Casdoor-only auth semantics.
    if cd.enabled and decode_token(token) is None:
        if verify_casdoor_jwt(token, cd):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Token refresh is not available when using Casdoor JWT",
            )

    token = create_access_token(
        user_id=str(current_user.id),
        username=current_user.username,
        is_superuser=current_user.is_superuser,
    )
    return TokenResponse(access_token=token, token_type="bearer")
