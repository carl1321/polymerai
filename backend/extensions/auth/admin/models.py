"""Pydantic models for admin user API (list, get, create, update)."""

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UserListItem(BaseModel):
    """User item in list response."""

    id: UUID
    username: str
    email: str
    real_name: str | None = None
    phone: str | None = None
    organization_id: UUID | None = None
    department_id: UUID | None = None
    organization_name: str | None = None
    department_name: str | None = None
    is_superuser: bool = False
    is_active: bool = True
    data_permission_level: str = "self"
    last_login_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    """Paginated list of users."""

    items: list[UserListItem]
    total: int
    page: int
    page_size: int


class UserCreateRequest(BaseModel):
    """Create user request body."""

    username: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=1)
    real_name: str | None = None
    phone: str | None = None
    organization_id: UUID | None = None
    department_id: UUID | None = None
    is_superuser: bool = False
    is_active: bool = True
    data_permission_level: str = "self"
    role_ids: list[UUID] = []


class UserUpdateRequest(BaseModel):
    """Update user request body (all optional)."""

    email: EmailStr | None = None
    password: str | None = None
    real_name: str | None = None
    phone: str | None = None
    organization_id: UUID | None = None
    department_id: UUID | None = None
    is_superuser: bool | None = None
    is_active: bool | None = None
    data_permission_level: str | None = None
    role_ids: list[UUID] | None = None
