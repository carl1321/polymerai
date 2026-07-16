"""Admin user API: list, get, create, update, delete at /api/admin/users."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from extensions.auth.admin.models import (
    UserCreateRequest,
    UserListItem,
    UserListResponse,
    UserUpdateRequest,
)
from extensions.auth.db import UserDB
from extensions.auth.dependencies import CurrentUser, require_admin
from extensions.auth.password import hash_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


def _serialize_user_row(row: dict) -> dict:
    """Convert DB row (with datetime/UUID) to JSON-serializable dict."""
    out = {}
    for k, v in row.items():
        if v is None:
            out[k] = None
        elif hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif isinstance(v, UUID):
            out[k] = str(v)
        else:
            out[k] = v
    return out


@router.get("", response_model=UserListResponse)
async def list_users(
    current_user: CurrentUser = Depends(require_admin),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    username: str | None = Query(None),
    is_active: bool | None = Query(None),
) -> UserListResponse:
    """List users with pagination and optional filters."""
    items, total = UserDB.list_users(
        page=page,
        page_size=page_size,
        username=username,
        is_active=is_active,
    )
    return UserListResponse(
        items=[UserListItem(**_serialize_user_row(r)) for r in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{user_id}")
async def get_user(
    user_id: UUID,
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """Get user by id."""
    user = UserDB.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    roles = UserDB.get_user_roles(user_id)
    out = _serialize_user_row(user)
    out.pop("ragflow_key", None)
    out["roles"] = [_serialize_user_row(r) for r in roles]
    return out


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreateRequest,
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """Create a new user."""
    created = UserDB.create_user(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        real_name=body.real_name,
        phone=body.phone,
        organization_id=body.organization_id,
        department_id=body.department_id,
        is_superuser=body.is_superuser,
        is_active=body.is_active,
        data_permission_level=body.data_permission_level,
    )
    if not created:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already exists (username or email conflict)",
        )
    if body.role_ids:
        UserDB.set_user_roles(UUID(str(created["id"])), body.role_ids)
    return _serialize_user_row(created)


@router.put("/{user_id}")
async def update_user(
    user_id: UUID,
    body: UserUpdateRequest,
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """Update user by id."""
    existing = UserDB.get_by_id(user_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    password_hash = None
    if body.password is not None and body.password != "":
        password_hash = hash_password(body.password)
    updated = UserDB.update_user(
        user_id,
        email=body.email,
        real_name=body.real_name,
        phone=body.phone,
        organization_id=body.organization_id,
        department_id=body.department_id,
        is_superuser=body.is_superuser,
        is_active=body.is_active,
        data_permission_level=body.data_permission_level,
        password_hash=password_hash,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Update failed")
    if body.role_ids is not None:
        UserDB.set_user_roles(user_id, body.role_ids)
    out = _serialize_user_row(updated)
    out.pop("ragflow_key", None)
    return out


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    current_user: CurrentUser = Depends(require_admin),
) -> None:
    """Delete user by id."""
    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )
    ok = UserDB.delete_user(user_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
