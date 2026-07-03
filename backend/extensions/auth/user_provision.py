"""User provisioning for SSO (Casdoor, Sa-Token / ContiNew)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from extensions.auth.db import UserDB
from extensions.auth.password import hash_password

if TYPE_CHECKING:
    from deerflow.config.app_config import SaTokenConfig
    from extensions.auth.satoken import SatokenIdentity

logger = logging.getLogger(__name__)

SATOKEN_OAUTH_PROVIDER = "satoken"


def find_or_create_user(
    *,
    username: str,
    email: str | None,
    real_name: str | None,
    auto_create: bool,
    is_superuser: bool = False,
) -> dict | None:
    """Find local user by username, or create one if allowed."""
    user = UserDB.get_by_username(username)
    if user:
        return user

    if email:
        user_by_email = UserDB.get_by_email(email)
        if user_by_email:
            try:
                if real_name and not user_by_email.get("real_name"):
                    UserDB.update_user(user_by_email["id"], real_name=real_name)
            except Exception:
                pass
            return user_by_email

    if not auto_create:
        return None

    password_hash = hash_password(f"sso:{username}")
    safe_email = email or f"{username}@sso.local"
    if "*" in safe_email or not safe_email.strip():
        safe_email = f"{username}@sso.local"
    created = UserDB.create_user(
        username=username,
        email=safe_email,
        password_hash=password_hash,
        real_name=real_name,
        is_superuser=is_superuser,
        is_active=True,
    )
    if created:
        logger.info("Created local user for SSO login: %s", username)
        return UserDB.get_by_username(username) or created
    logger.error("Failed to create local user for SSO login: %s", username)
    return None


def _remote_implies_superuser(remote_role_codes: list[str], cfg: SaTokenConfig) -> bool:
    super_codes = {c.strip() for c in (cfg.superuser_role_codes or []) if c and str(c).strip()}
    return any(code in super_codes for code in remote_role_codes)


def _map_remote_role_codes(remote_role_codes: list[str], cfg: SaTokenConfig) -> list[str]:
    mapping = cfg.role_code_map or {}
    local: list[str] = []
    for remote in remote_role_codes:
        remote_str = str(remote).strip()
        if not remote_str:
            continue
        local.append(mapping.get(remote_str, remote_str))
    return local


def apply_satoken_roles(user_id: UUID, remote_role_codes: list[str], cfg: SaTokenConfig) -> dict | None:
    """Sync is_superuser, system_role, and user_roles from ContiNew role codes."""
    if not cfg.sync_roles_on_login:
        return UserDB.get_by_id(user_id)

    remote_super = _remote_implies_superuser(remote_role_codes, cfg)
    existing = UserDB.get_by_id(user_id)
    if existing and existing.get("is_superuser") and not remote_super and not cfg.sync_downgrade_superuser:
        is_superuser = True
    else:
        is_superuser = remote_super

    system_role = "admin" if is_superuser else "user"
    local_codes = _map_remote_role_codes(remote_role_codes, cfg)
    role_ids = UserDB.get_role_ids_by_codes(local_codes)
    if role_ids:
        UserDB.set_user_roles(user_id, role_ids)

    return UserDB.update_user(
        user_id,
        is_superuser=is_superuser,
        system_role=system_role,
    )


def resolve_satoken_user(identity: SatokenIdentity, cfg: SaTokenConfig) -> dict | None:
    """Resolve ContiNew identity to a local users row (lookup then optional create)."""
    user = UserDB.get_by_username(identity.username)
    if not user and identity.email:
        user = UserDB.get_by_email(identity.email)
    if not user and identity.login_id:
        user = UserDB.get_by_oauth(SATOKEN_OAUTH_PROVIDER, identity.login_id)

    if not user:
        remote_super = _remote_implies_superuser(list(identity.role_codes), cfg)
        user = find_or_create_user(
            username=identity.username,
            email=identity.email,
            real_name=identity.real_name,
            auto_create=cfg.auto_create_user,
            is_superuser=remote_super,
        )

    if not user:
        return None

    raw_id = user["id"]
    user_id = raw_id if isinstance(raw_id, UUID) else UUID(str(raw_id))

    link_kwargs: dict = {
        "oauth_provider": SATOKEN_OAUTH_PROVIDER,
        "oauth_id": identity.login_id,
    }
    if identity.real_name and not user.get("real_name"):
        link_kwargs["real_name"] = identity.real_name
    UserDB.update_user(user_id, **link_kwargs)

    updated = apply_satoken_roles(user_id, list(identity.role_codes), cfg)
    return updated or UserDB.get_by_id(user_id)
