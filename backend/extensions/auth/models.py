"""Pydantic models for auth API (login, me, refresh)."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    """Login request body."""

    username: str
    password: str


class RoleResponse(BaseModel):
    """Role in user response."""

    id: UUID
    code: str
    name: str
    description: str | None = None
    is_system: bool = False
    is_active: bool = True
    sort_order: int = 0
    created_at: str | None = None
    updated_at: str | None = None

    class Config:
        from_attributes = True


class UserWithRoles(BaseModel):
    """User with roles for login response."""

    id: UUID
    username: str
    email: str
    real_name: str | None = None
    is_superuser: bool = False
    roles: list[RoleResponse] = []
    permissions: list[str] = []
    organization_id: UUID | None = None
    department_id: UUID | None = None
    data_permission_level: str = "self"
    is_active: bool = True
    last_login_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    """Login response."""

    access_token: str
    token_type: str = "bearer"
    user: dict[str, Any]  # UserWithRoles-like dict (id, username, email, roles, permissions, ...)


class TokenResponse(BaseModel):
    """Refresh token response."""

    access_token: str
    token_type: str = "bearer"


class UserInfoResponse(BaseModel):
    """Current user info (/me). Menus omitted in step 1 (no menus table)."""

    id: UUID
    username: str
    email: str
    real_name: str | None = None
    is_superuser: bool = False
    roles: list[RoleResponse] = []
    permissions: list[str] = []
    menus: list[Any] = []  # Empty until menus table added
    organization: Any | None = None
    department: Any | None = None
    data_permission_level: str = "self"

    class Config:
        from_attributes = True
