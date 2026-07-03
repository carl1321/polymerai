"""FastAPI dependencies for auth: CurrentUser, get_current_user, get_current_user_optional."""

import logging
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from deerflow.config.app_config import CasdoorConfig, SaTokenConfig, get_app_config
from extensions.auth.casdoor import pick_identity as casdoor_pick_identity
from extensions.auth.casdoor import verify_casdoor_jwt
from extensions.auth.db import TokenBlacklist, UserDB
from extensions.auth.jwt import decode_token, get_token_jti
from extensions.auth.satoken import extract_token_from_request, validate_satoken_token_sync
from extensions.auth.user_provision import resolve_satoken_user

logger = logging.getLogger(__name__)

_optional_bearer = HTTPBearer(auto_error=False)


class CurrentUser:
    """Current user with roles and permissions."""

    def __init__(self, user_data: dict[str, Any], roles: list, permissions: list[str]) -> None:
        raw_id = user_data["id"]
        self.id = raw_id if isinstance(raw_id, UUID) else UUID(str(raw_id))
        self.username = user_data.get("username", "")
        self.email = user_data.get("email", "")
        self.real_name = user_data.get("real_name")
        self.is_superuser = user_data.get("is_superuser", False)
        self.organization_id = user_data.get("organization_id")
        self.department_id = user_data.get("department_id")
        self.data_permission_level = user_data.get("data_permission_level", "self")
        self.roles = roles
        self.permissions = permissions

    def has_permission(self, permission_code: str) -> bool:
        if self.is_superuser:
            return True
        return permission_code in self.permissions

    def has_role(self, role_code: str) -> bool:
        if self.is_superuser:
            return True
        return any(r.get("code") == role_code for r in self.roles)


def _unauthorized_bearer(detail: str = "Invalid authentication token") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _current_user_from_deerflow_token(token: str) -> CurrentUser:
    payload = decode_token(token)
    if not payload:
        raise _unauthorized_bearer()
    token_jti = get_token_jti(token)
    if token_jti and TokenBlacklist.is_blacklisted(token_jti):
        raise _unauthorized_bearer("Token has been revoked")
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise _unauthorized_bearer("Invalid token payload")
    try:
        user_id = UUID(user_id_str)
    except ValueError:
        raise _unauthorized_bearer("Invalid user ID in token")
    user_data = UserDB.get_by_id(user_id)
    if not user_data:
        raise _unauthorized_bearer("User not found")
    if not user_data.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )
    roles = UserDB.get_user_roles(user_id)
    permissions = UserDB.get_user_permissions(user_id)
    return CurrentUser(user_data, roles, permissions)


def _casdoor_verifier_configured(cd: CasdoorConfig) -> bool:
    """True when Casdoor is enabled (casdoor JWT decode does not require PEM)."""
    return bool(cd.enabled)


def _try_current_user_from_casdoor_token(token: str, cd: CasdoorConfig) -> CurrentUser | None:
    """Return CurrentUser if token is a valid Casdoor JWT and user resolves; else None."""
    if not cd.enabled or not _casdoor_verifier_configured(cd):
        return None
    try:
        return _current_user_from_casdoor_token(token, cd)
    except HTTPException:
        return None


def _current_user_from_deerflow_token_optional(token: str) -> CurrentUser | None:
    """DeerFlow JWT → user, or None (no exception)."""
    payload = decode_token(token)
    if not payload:
        return None
    token_jti = get_token_jti(token)
    if token_jti and TokenBlacklist.is_blacklisted(token_jti):
        return None
    user_id_str = payload.get("sub")
    if not user_id_str:
        return None
    try:
        user_id = UUID(user_id_str)
    except ValueError:
        return None
    user_data = UserDB.get_by_id(user_id)
    if not user_data or not user_data.get("is_active", True):
        return None
    roles = UserDB.get_user_roles(user_id)
    permissions = UserDB.get_user_permissions(user_id)
    return CurrentUser(user_data, roles, permissions)


def _current_user_from_casdoor_token(token: str, cd: CasdoorConfig) -> CurrentUser:
    payload = verify_casdoor_jwt(token, cd)
    if not payload:
        raise _unauthorized_bearer()
    from extensions.auth.user_provision import find_or_create_user

    username, email, real_name = casdoor_pick_identity(payload)
    user_data = UserDB.get_by_username(username)
    if not user_data:
        user_data = find_or_create_user(
            username=username,
            email=email,
            real_name=real_name,
            auto_create=cd.auto_create_user,
        )
    if not user_data:
        raise _unauthorized_bearer("User not provisioned")
    if not user_data.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )
    raw_id = user_data["id"]
    user_id = raw_id if isinstance(raw_id, UUID) else UUID(str(raw_id))
    roles = UserDB.get_user_roles(user_id)
    permissions = UserDB.get_user_permissions(user_id)
    return CurrentUser(user_data, roles, permissions)


def _try_current_user_from_satoken(token: str, st: SaTokenConfig, request: Request | None = None) -> CurrentUser | None:
    if not st.enabled:
        return None
    identity = validate_satoken_token_sync(token, st, request=request)
    if identity is None:
        return None
    user_data = resolve_satoken_user(identity, st)
    if not user_data:
        return None
    if not user_data.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )
    raw_id = user_data["id"]
    user_id = raw_id if isinstance(raw_id, UUID) else UUID(str(raw_id))
    roles = UserDB.get_user_roles(user_id)
    permissions = UserDB.get_user_permissions(user_id)
    return CurrentUser(user_data, roles, permissions)


def resolve_bearer_user(
    token: str,
    *,
    optional: bool,
    request: Request | None = None,
) -> CurrentUser | None:
    """Resolve Bearer: Casdoor JWT, Sa-Token remote (when enabled), then DeerFlow JWT."""
    cfg = get_app_config()
    cd = cfg.auth.casdoor
    st = cfg.auth.satoken

    if cd.enabled and _casdoor_verifier_configured(cd):
        u = _try_current_user_from_casdoor_token(token, cd)
        if u is not None:
            return u

    if st.enabled:
        try:
            u = _try_current_user_from_satoken(token, st, request=request)
        except HTTPException:
            if optional:
                return None
            raise
        if u is not None:
            return u

    deerflow_user = _current_user_from_deerflow_token_optional(token)
    if deerflow_user is not None:
        return deerflow_user

    if optional:
        return None
    raise _unauthorized_bearer()


def resolve_user_from_request(request: Request, *, optional: bool) -> CurrentUser | None:
    """Resolve user from request headers/cookies."""
    cfg = get_app_config()
    token = extract_token_from_request(request, token_name=cfg.auth.satoken.token_name)
    if not token:
        if optional:
            return None
        raise _unauthorized_bearer("Not authenticated")
    return resolve_bearer_user(token, optional=optional, request=request)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> CurrentUser:
    """Require valid token and return current user."""
    stamped = getattr(request.state, "user", None)
    if isinstance(stamped, CurrentUser):
        return stamped
    if credentials and credentials.credentials:
        user = resolve_bearer_user(credentials.credentials, optional=False, request=request)
        if user is not None:
            return user
    user = resolve_user_from_request(request, optional=False)
    if user is None:
        raise _unauthorized_bearer()
    return user


async def get_current_user_optional(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> CurrentUser | None:
    """Optional auth: return CurrentUser or None."""
    stamped = getattr(request.state, "user", None)
    if isinstance(stamped, CurrentUser):
        return stamped
    if credentials and credentials.credentials:
        user = resolve_bearer_user(credentials.credentials, optional=True, request=request)
        if user is not None:
            return user
    return resolve_user_from_request(request, optional=True)


async def require_admin(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Require superuser or admin role."""
    if current_user.is_superuser or current_user.has_role("admin"):
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin access required",
    )
