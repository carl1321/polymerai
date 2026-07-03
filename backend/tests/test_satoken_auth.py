from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from extensions.auth.dependencies import resolve_bearer_user
from extensions.auth.satoken import (
    SatokenIdentity,
    _is_validate_success,
    normalize_authorization_value,
    pick_identity,
    pick_roles,
)
from extensions.auth.user_provision import apply_satoken_roles, resolve_satoken_user


@dataclass
class _SaTokenCfg:
    enabled: bool = True
    endpoint: str = "http://auth.example.com"
    validate_path: str = "/auth/user/info"
    token_name: str = "Authorization"
    token_prefix: str = "Bearer"
    tenant_header: str | None = "X-Tenant-Code"
    tenant_code: str | None = None
    allow_local_login: bool = True
    auto_create_user: bool = True
    timeout_seconds: float = 5.0
    validate_api_key: str | None = None
    login_id_field: str = "id"
    username_field: str = "username"
    email_field: str = "email"
    real_name_field: str = "nickname"
    roles_field: str | None = "roles"
    superuser_role_codes: list[str] = field(default_factory=lambda: ["super_admin", "sys_admin", "admin"])
    role_code_map: dict[str, str] = field(default_factory=lambda: {"super_admin": "admin", "sys_admin": "admin", "admin": "admin"})
    sync_roles_on_login: bool = True
    sync_downgrade_superuser: bool = True
    cache_ttl_seconds: int = 60


@dataclass
class _CasdoorCfg:
    enabled: bool = False


@dataclass
class _AuthCfg:
    casdoor: _CasdoorCfg = field(default_factory=_CasdoorCfg)
    satoken: _SaTokenCfg = field(default_factory=_SaTokenCfg)


@dataclass
class _AppCfg:
    auth: _AuthCfg = field(default_factory=_AuthCfg)


def _make_app() -> FastAPI:
    from extensions.auth.routes import router as auth_router

    app = FastAPI()
    app.include_router(auth_router)
    return app


@pytest.fixture()
def client() -> TestClient:
    with TestClient(_make_app()) as c:
        yield c


class TestSaTokenHelpers:
    def test_normalize_authorization_avoids_double_bearer(self) -> None:
        assert normalize_authorization_value("abc", "Bearer") == "Bearer abc"
        assert normalize_authorization_value("Bearer abc", "Bearer") == "Bearer abc"

    def test_is_validate_success_accepts_continew_code_zero(self) -> None:
        assert _is_validate_success({"code": "0", "success": True, "data": {}}) is True
        assert _is_validate_success({"code": 200, "data": {}}) is True
        assert _is_validate_success({"code": "401", "success": False}) is False

    def test_pick_identity_uses_remote_username(self) -> None:
        cfg = _SaTokenCfg()
        login_id, username, email, real_name = pick_identity(
            {"id": 1001, "username": "admin", "email": "a@b.com", "nickname": "Admin"},
            cfg,
        )
        assert login_id == "1001"
        assert username == "admin"
        assert email == "a@b.com"
        assert real_name == "Admin"

    def test_pick_roles_reads_roles_field(self) -> None:
        cfg = _SaTokenCfg()
        assert pick_roles({"roles": ["super_admin", "user"]}, cfg) == ["super_admin", "user"]


class TestSaTokenRoleSync:
    def test_apply_satoken_roles_sys_admin_is_superuser(self) -> None:
        uid = uuid4()
        cfg = _SaTokenCfg()

        with (
            patch("extensions.auth.user_provision.UserDB.get_by_id") as get_by_id,
            patch("extensions.auth.user_provision.UserDB.get_role_ids_by_codes", return_value=[]),
            patch("extensions.auth.user_provision.UserDB.update_user") as update_user,
        ):
            get_by_id.return_value = {"id": uid, "is_superuser": False}
            update_user.return_value = {"id": uid, "is_superuser": True, "system_role": "admin"}
            row = apply_satoken_roles(uid, ["sys_admin"], cfg)

        assert row is not None
        assert update_user.call_args.kwargs["is_superuser"] is True

    def test_apply_satoken_roles_sets_superuser(self) -> None:
        uid = uuid4()
        admin_role_id = uuid4()
        cfg = _SaTokenCfg()

        with (
            patch("extensions.auth.user_provision.UserDB.get_by_id") as get_by_id,
            patch("extensions.auth.user_provision.UserDB.get_role_ids_by_codes", return_value=[admin_role_id]),
            patch("extensions.auth.user_provision.UserDB.set_user_roles") as set_roles,
            patch("extensions.auth.user_provision.UserDB.update_user") as update_user,
        ):
            get_by_id.return_value = {"id": uid, "is_superuser": False}
            update_user.return_value = {
                "id": uid,
                "username": "admin",
                "is_superuser": True,
                "system_role": "admin",
                "is_active": True,
            }
            row = apply_satoken_roles(uid, ["super_admin"], cfg)

        assert row is not None
        assert row["is_superuser"] is True
        set_roles.assert_called_once_with(uid, [admin_role_id])
        update_user.assert_called_once()
        assert update_user.call_args.kwargs["is_superuser"] is True
        assert update_user.call_args.kwargs["system_role"] == "admin"

    def test_resolve_satoken_user_prefers_username_lookup(self) -> None:
        uid = uuid4()
        cfg = _SaTokenCfg()
        identity = SatokenIdentity(
            login_id="1",
            username="admin",
            email="admin@example.com",
            real_name="Admin",
            role_codes=("super_admin",),
            raw={},
        )
        admin_row = {"id": uid, "username": "admin", "is_active": True, "is_superuser": True}

        with (
            patch("extensions.auth.user_provision.UserDB.get_by_username", return_value=admin_row) as by_name,
            patch("extensions.auth.user_provision.UserDB.get_by_email") as by_email,
            patch("extensions.auth.user_provision.UserDB.get_by_oauth") as by_oauth,
            patch("extensions.auth.user_provision.find_or_create_user") as create,
            patch("extensions.auth.user_provision.UserDB.update_user", return_value=admin_row),
            patch("extensions.auth.user_provision.apply_satoken_roles", return_value=admin_row),
        ):
            user = resolve_satoken_user(identity, cfg)

        assert user is not None
        assert user["username"] == "admin"
        by_name.assert_called_once_with("admin")
        by_email.assert_not_called()
        by_oauth.assert_not_called()
        create.assert_not_called()


class TestSaTokenAuth:
    def test_enabled_endpoint(self, client: TestClient) -> None:
        with patch("extensions.auth.routes.get_app_config", return_value=_AppCfg()):
            res = client.get("/api/auth/satoken/enabled")
        assert res.status_code == 200
        assert res.json() == {"enabled": True, "allow_local_login": True}

    def test_login_blocked_when_local_disabled(self, client: TestClient) -> None:
        cfg = _AppCfg()
        cfg.auth.satoken.allow_local_login = False
        with patch("extensions.auth.routes.get_app_config", return_value=cfg):
            res = client.post(
                "/api/auth/login",
                json={"username": "admin", "password": "secret"},
            )
        assert res.status_code == 403

    def test_resolve_bearer_user_from_satoken_continew_code_zero(self) -> None:
        uid = uuid4()
        cfg = _AppCfg()

        class _Resp:
            status_code = 200

            @staticmethod
            def json() -> dict:
                return {
                    "code": "0",
                    "success": True,
                    "data": {
                        "id": 1,
                        "username": "admin",
                        "email": "admin@example.com",
                        "nickname": "Admin",
                        "roles": ["super_admin"],
                    },
                }

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = _Resp()

        with (
            patch("extensions.auth.dependencies.get_app_config", return_value=cfg),
            patch("extensions.auth.jwt.decode_token", return_value=None),
            patch("extensions.auth.satoken.httpx.Client", return_value=mock_client),
            patch(
                "extensions.auth.dependencies.resolve_satoken_user",
                return_value={
                    "id": uid,
                    "username": "admin",
                    "email": "admin@example.com",
                    "is_active": True,
                    "is_superuser": True,
                },
            ),
            patch("extensions.auth.dependencies.UserDB.get_user_roles", return_value=[{"code": "admin"}]),
            patch("extensions.auth.dependencies.UserDB.get_user_permissions", return_value=[]),
        ):
            user = resolve_bearer_user("remote-token", optional=False)

        assert user is not None
        assert user.username == "admin"
        assert user.is_superuser is True

    def test_resolve_bearer_user_satoken_jwt_shape_tried_before_local_jwt(self) -> None:
        """Sa-Token tokens are JWT-shaped; remote validate runs before local JWT decode."""
        uid = uuid4()
        cfg = _AppCfg()
        jwt_like = "aaa.bbb.ccc"

        with (
            patch("extensions.auth.dependencies.get_app_config", return_value=cfg),
            patch("extensions.auth.jwt.decode_token") as decode,
            patch(
                "extensions.auth.dependencies.resolve_satoken_user",
                return_value={
                    "id": uid,
                    "username": "zxw1321",
                    "email": "zxw@example.com",
                    "is_active": True,
                    "is_superuser": True,
                },
            ),
            patch("extensions.auth.dependencies.validate_satoken_token_sync") as validate,
            patch("extensions.auth.dependencies.UserDB.get_user_roles", return_value=[]),
            patch("extensions.auth.dependencies.UserDB.get_user_permissions", return_value=[]),
        ):
            identity = MagicMock()
            validate.return_value = identity
            user = resolve_bearer_user(jwt_like, optional=False)

        assert user is not None
        assert user.username == "zxw1321"
        validate.assert_called_once()
        decode.assert_not_called()

    def test_resolve_bearer_user_falls_back_to_local_jwt_when_satoken_invalid(self) -> None:
        uid = uuid4()
        cfg = _AppCfg()

        with (
            patch("extensions.auth.dependencies.get_app_config", return_value=cfg),
            patch("extensions.auth.dependencies.validate_satoken_token_sync", return_value=None),
            patch(
                "extensions.auth.dependencies.decode_token",
                return_value={"sub": str(uid), "username": "admin", "is_superuser": True, "jti": "jti"},
            ),
            patch("extensions.auth.dependencies.get_token_jti", return_value=None),
            patch(
                "extensions.auth.dependencies.UserDB.get_by_id",
                return_value={"id": uid, "username": "admin", "is_active": True, "is_superuser": True},
            ),
            patch("extensions.auth.dependencies.UserDB.get_user_roles", return_value=[]),
            patch("extensions.auth.dependencies.UserDB.get_user_permissions", return_value=[]),
        ):
            user = resolve_bearer_user("local-jwt-token", optional=False)

        assert user is not None
        assert user.username == "admin"

    def test_resolve_bearer_user_from_satoken(self) -> None:
        uid = uuid4()
        cfg = _AppCfg()

        class _Resp:
            status_code = 200

            @staticmethod
            def json() -> dict:
                return {
                    "code": 200,
                    "data": {
                        "id": 1001,
                        "username": "admin",
                        "email": "admin@example.com",
                        "nickname": "Admin",
                        "roles": ["admin"],
                    },
                }

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = _Resp()

        with (
            patch("extensions.auth.dependencies.get_app_config", return_value=cfg),
            patch("extensions.auth.jwt.decode_token", return_value=None),
            patch("extensions.auth.satoken.httpx.Client", return_value=mock_client),
            patch(
                "extensions.auth.dependencies.resolve_satoken_user",
                return_value={
                    "id": uid,
                    "username": "admin",
                    "email": "admin@example.com",
                    "is_active": True,
                    "is_superuser": True,
                },
            ),
            patch("extensions.auth.dependencies.UserDB.get_user_roles", return_value=[]),
            patch("extensions.auth.dependencies.UserDB.get_user_permissions", return_value=[]),
        ):
            user = resolve_bearer_user("remote-token-1001", optional=False)

        assert user is not None
        assert user.username == "admin"
        mock_client.get.assert_called_once()
        call_kwargs = mock_client.get.call_args.kwargs
        assert call_kwargs["headers"]["Authorization"] == "Bearer remote-token-1001"

    def test_resolve_bearer_user_satoken_invalid(self) -> None:
        cfg = _AppCfg()

        class _Resp:
            status_code = 401

            @staticmethod
            def json() -> dict:
                return {"code": 401, "msg": "unauthorized"}

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = _Resp()

        with (
            patch("extensions.auth.dependencies.get_app_config", return_value=cfg),
            patch("extensions.auth.jwt.decode_token", return_value=None),
            patch("extensions.auth.satoken.httpx.Client", return_value=mock_client),
            pytest.raises(HTTPException),
        ):
            resolve_bearer_user("bad-token", optional=False)

    def test_logout_accepts_satoken_when_deerflow_decode_fails(self, client: TestClient) -> None:
        cfg = _AppCfg()

        class _Resp:
            status_code = 200

            @staticmethod
            def json() -> dict:
                return {"code": 200, "data": {"id": 1, "username": "u"}}

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = _Resp()

        with (
            patch("extensions.auth.routes.get_app_config", return_value=cfg),
            patch("extensions.auth.routes.decode_token", return_value=None),
            patch("extensions.auth.routes.verify_casdoor_jwt", return_value=None),
            patch("extensions.auth.satoken.validate_satoken_token_sync", return_value=MagicMock()),
        ):
            res = client.post("/api/auth/logout", headers={"Authorization": "Bearer remote"})
        assert res.status_code == 200
