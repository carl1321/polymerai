"""Database utilities for auth: UserDB and TokenBlacklist using app database."""

import logging
from typing import Any
from uuid import UUID

from extensions._core.app_db import get_app_db_connection

logger = logging.getLogger(__name__)


class UserDB:
    """User database operations."""

    @staticmethod
    def get_by_username(username: str) -> dict[str, Any] | None:
        """Get user by username."""
        try:
            conn = get_app_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT u.*,
                               o.name as organization_name,
                               d.name as department_name
                        FROM users u
                        LEFT JOIN organizations o ON u.organization_id = o.id
                        LEFT JOIN departments d ON u.department_id = d.id
                        WHERE u.username = %s
                        """,
                        (username,),
                    )
                    return cursor.fetchone()
            finally:
                conn.close()
        except Exception as e:
            logger.error("Error getting user by username: %s", e)
            return None

    @staticmethod
    def get_by_email(email: str) -> dict[str, Any] | None:
        """Get user by email."""
        try:
            conn = get_app_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT u.*,
                               o.name as organization_name,
                               d.name as department_name
                        FROM users u
                        LEFT JOIN organizations o ON u.organization_id = o.id
                        LEFT JOIN departments d ON u.department_id = d.id
                        WHERE u.email = %s
                        """,
                        (email,),
                    )
                    return cursor.fetchone()
            finally:
                conn.close()
        except Exception as e:
            logger.error("Error getting user by email: %s", e)
            return None

    @staticmethod
    def get_by_oauth(provider: str, oauth_id: str) -> dict[str, Any] | None:
        """Get user by SSO provider + external login id."""
        if not provider or not oauth_id:
            return None
        try:
            conn = get_app_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT u.*,
                               o.name as organization_name,
                               d.name as department_name
                        FROM users u
                        LEFT JOIN organizations o ON u.organization_id = o.id
                        LEFT JOIN departments d ON u.department_id = d.id
                        WHERE u.oauth_provider = %s AND u.oauth_id = %s
                        """,
                        (provider.strip(), str(oauth_id).strip()),
                    )
                    return cursor.fetchone()
            finally:
                conn.close()
        except Exception as e:
            logger.error("Error getting user by oauth: %s", e)
            return None

    @staticmethod
    def get_by_id(user_id: UUID) -> dict[str, Any] | None:
        """Get user by ID."""
        try:
            conn = get_app_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT u.*,
                               o.name as organization_name,
                               d.name as department_name
                        FROM users u
                        LEFT JOIN organizations o ON u.organization_id = o.id
                        LEFT JOIN departments d ON u.department_id = d.id
                        WHERE u.id = %s
                        """,
                        (str(user_id),),
                    )
                    return cursor.fetchone()
            finally:
                conn.close()
        except Exception as e:
            logger.error("Error getting user by ID: %s", e)
            return None

    @staticmethod
    def get_role_ids_by_codes(codes: list[str]) -> list[UUID]:
        """Resolve local role UUIDs for the given role codes (unknown codes skipped)."""
        if not codes:
            return []
        try:
            conn = get_app_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT id FROM roles
                        WHERE code = ANY(%s) AND is_active = true
                        """,
                        (codes,),
                    )
                    rows = cursor.fetchall()
                    out: list[UUID] = []
                    for row in rows:
                        rid = row["id"]
                        out.append(rid if isinstance(rid, UUID) else UUID(str(rid)))
                    return out
            finally:
                conn.close()
        except Exception as e:
            logger.error("Error resolving role ids by codes: %s", e)
            return []

    @staticmethod
    def get_user_roles(user_id: UUID) -> list[dict[str, Any]]:
        """Get user's roles."""
        try:
            conn = get_app_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT r.*
                        FROM roles r
                        INNER JOIN user_roles ur ON r.id = ur.role_id
                        WHERE ur.user_id = %s AND r.is_active = true
                        ORDER BY r.sort_order
                        """,
                        (str(user_id),),
                    )
                    return cursor.fetchall()
            finally:
                conn.close()
        except Exception as e:
            logger.error("Error getting user roles: %s", e)
            return []

    @staticmethod
    def get_user_permissions(user_id: UUID) -> list[str]:
        """Get user's permission codes."""
        try:
            conn = get_app_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT DISTINCT p.code
                        FROM permissions p
                        INNER JOIN role_permissions rp ON p.id = rp.permission_id
                        INNER JOIN user_roles ur ON rp.role_id = ur.role_id
                        WHERE ur.user_id = %s
                        ORDER BY p.code
                        """,
                        (str(user_id),),
                    )
                    return [row["code"] for row in cursor.fetchall()]
            finally:
                conn.close()
        except Exception as e:
            logger.error("Error getting user permissions: %s", e)
            return []

    @staticmethod
    def update_last_login(user_id: UUID) -> None:
        """Update user's last login time."""
        try:
            conn = get_app_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE users SET last_login_at = NOW() WHERE id = %s",
                        (str(user_id),),
                    )
                    conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.error("Error updating last login: %s", e)

    @staticmethod
    def list_users(
        *,
        page: int = 1,
        page_size: int = 20,
        username: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """List users with optional filters; returns (items, total_count)."""
        try:
            conn = get_app_db_connection()
            try:
                with conn.cursor() as cursor:
                    where_parts: list[str] = []
                    params: list[Any] = []
                    if username is not None and username.strip():
                        where_parts.append("u.username ILIKE %s")
                        params.append(f"%{username.strip()}%")
                    if is_active is not None:
                        where_parts.append("u.is_active = %s")
                        params.append(is_active)
                    where_sql = " AND ".join(where_parts) if where_parts else "1=1"
                    count_sql = f"SELECT COUNT(*) AS total FROM users u WHERE {where_sql}"
                    cursor.execute(count_sql, params)
                    row = cursor.fetchone()
                    total = int(row["total"]) if row else 0
                    offset = (page - 1) * page_size
                    params.extend([page_size, offset])
                    cursor.execute(
                        f"""
                        SELECT u.id, u.username, u.email, u.real_name, u.phone,
                               u.organization_id, u.department_id, u.is_superuser, u.is_active,
                               u.data_permission_level, u.last_login_at, u.created_at, u.updated_at,
                               o.name as organization_name, d.name as department_name
                        FROM users u
                        LEFT JOIN organizations o ON u.organization_id = o.id
                        LEFT JOIN departments d ON u.department_id = d.id
                        WHERE {where_sql}
                        ORDER BY u.created_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        params,
                    )
                    rows = cursor.fetchall()
                    return [dict(r) for r in rows], total
            finally:
                conn.close()
        except Exception as e:
            logger.error("Error listing users: %s", e)
            return [], 0

    @staticmethod
    def create_user(
        *,
        username: str,
        email: str,
        password_hash: str,
        real_name: str | None = None,
        phone: str | None = None,
        organization_id: UUID | None = None,
        department_id: UUID | None = None,
        is_superuser: bool = False,
        is_active: bool = True,
        data_permission_level: str = "self",
    ) -> dict[str, Any] | None:
        """Create a user; returns created user row or None on conflict/error."""
        from uuid import uuid4

        new_id = str(uuid4())
        try:
            conn = get_app_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO users (
                            id, username, email, password_hash, real_name, phone,
                            organization_id, department_id, is_superuser, is_active, data_permission_level,
                            system_role, needs_setup, token_version, created_at, updated_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, NOW(), NOW()
                        )
                        RETURNING id, username, email, real_name, phone, organization_id, department_id,
                                  is_superuser, is_active, data_permission_level, last_login_at, created_at, updated_at
                        """,
                        (
                            new_id,
                            username.strip(),
                            email.strip(),
                            password_hash,
                            real_name.strip() if real_name else None,
                            phone.strip() if phone else None,
                            str(organization_id) if organization_id else None,
                            str(department_id) if department_id else None,
                            is_superuser,
                            is_active,
                            data_permission_level or "self",
                            "admin" if is_superuser else "user",
                            False,
                            0,
                        ),
                    )
                    row = cursor.fetchone()
                    conn.commit()
                    return dict(row) if row else None
            finally:
                conn.close()
        except Exception as e:
            logger.error("Error creating user: %s", e)
            return None

    @staticmethod
    def update_user(
        user_id: UUID,
        *,
        email: str | None = None,
        real_name: str | None = None,
        phone: str | None = None,
        organization_id: UUID | None = None,
        department_id: UUID | None = None,
        is_superuser: bool | None = None,
        is_active: bool | None = None,
        data_permission_level: str | None = None,
        password_hash: str | None = None,
        ragflow_key: str | None = None,
        system_role: str | None = None,
        oauth_provider: str | None = None,
        oauth_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Update user by id; returns updated user row or None."""
        try:
            conn = get_app_db_connection()
            try:
                with conn.cursor() as cursor:
                    updates: list[str] = ["updated_at = NOW()"]
                    params: list[Any] = []
                    if email is not None:
                        updates.append("email = %s")
                        params.append(email.strip())
                    if real_name is not None:
                        updates.append("real_name = %s")
                        params.append(real_name.strip() if real_name else None)
                    if phone is not None:
                        updates.append("phone = %s")
                        params.append(phone.strip() if phone else None)
                    if organization_id is not None:
                        updates.append("organization_id = %s")
                        params.append(str(organization_id) if organization_id else None)
                    if department_id is not None:
                        updates.append("department_id = %s")
                        params.append(str(department_id) if department_id else None)
                    if is_superuser is not None:
                        updates.append("is_superuser = %s")
                        params.append(is_superuser)
                    if is_active is not None:
                        updates.append("is_active = %s")
                        params.append(is_active)
                    if data_permission_level is not None:
                        updates.append("data_permission_level = %s")
                        params.append(data_permission_level)
                    if password_hash is not None:
                        updates.append("password_hash = %s")
                        params.append(password_hash)
                    if ragflow_key is not None:
                        updates.append("ragflow_key = %s")
                        params.append(ragflow_key.strip() if ragflow_key else None)
                    if system_role is not None:
                        updates.append("system_role = %s")
                        params.append(system_role)
                    if oauth_provider is not None:
                        updates.append("oauth_provider = %s")
                        params.append(oauth_provider.strip() if oauth_provider else None)
                    if oauth_id is not None:
                        updates.append("oauth_id = %s")
                        params.append(str(oauth_id).strip() if oauth_id else None)
                    if len(params) == 0:
                        return UserDB.get_by_id(user_id)
                    params.append(str(user_id))
                    cursor.execute(
                        f"""
                        UPDATE users SET {", ".join(updates)}
                        WHERE id = %s
                        RETURNING id, username, email, real_name, phone, organization_id, department_id,
                                  is_superuser, is_active, data_permission_level, last_login_at, created_at, updated_at
                        """,
                        params,
                    )
                    row = cursor.fetchone()
                    conn.commit()
                    return dict(row) if row else None
            finally:
                conn.close()
        except Exception as e:
            logger.error("Error updating user: %s", e)
            return None

    @staticmethod
    def delete_user(user_id: UUID) -> bool:
        """Delete user by id; returns True if deleted."""
        try:
            conn = get_app_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM users WHERE id = %s", (str(user_id),))
                    conn.commit()
                    return cursor.rowcount > 0
            finally:
                conn.close()
        except Exception as e:
            logger.error("Error deleting user: %s", e)
            return False

    @staticmethod
    def set_user_roles(user_id: UUID, role_ids: list[UUID]) -> None:
        """Replace user's roles with the given role ids."""
        try:
            conn = get_app_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM user_roles WHERE user_id = %s", (str(user_id),))
                    for rid in role_ids:
                        cursor.execute(
                            "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s) ON CONFLICT (user_id, role_id) DO NOTHING",
                            (str(user_id), str(rid)),
                        )
                    conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.error("Error setting user roles: %s", e)


class TokenBlacklist:
    """Token blacklist (logout) using user_sessions table."""

    @staticmethod
    def add_token(token_jti: str, user_id: UUID, expires_at: Any) -> None:
        """Add token to blacklist."""
        try:
            conn = get_app_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO user_sessions (user_id, token_jti, expires_at)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (token_jti) DO NOTHING
                        """,
                        (str(user_id), token_jti, expires_at),
                    )
                    conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.error("Error adding token to blacklist: %s", e)

    @staticmethod
    def is_blacklisted(token_jti: str) -> bool:
        """Check if token is blacklisted."""
        try:
            conn = get_app_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT 1 FROM user_sessions
                        WHERE token_jti = %s AND expires_at > NOW()
                        """,
                        (token_jti,),
                    )
                    return cursor.fetchone() is not None
            finally:
                conn.close()
        except Exception as e:
            logger.error("Error checking token blacklist: %s", e)
            return False
