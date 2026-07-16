from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import jwt as pyjwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import FastAPI
from fastapi.testclient import TestClient

from deerflow.config.app_config import CasdoorConfig
from extensions.auth.casdoor import verify_casdoor_jwt
from extensions.auth.dependencies import CurrentUser, get_current_user


@dataclass
class _CasdoorCfg:
    enabled: bool = True
    endpoint: str = "https://casdoor.example.com"
    client_id: str = "cid"
    client_secret: str = "csec"
    organization_name: str = "org"
    application_name: str = "app"
    certificate: str = "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----"
    redirect_uri: str | None = None
    auto_create_user: bool = True
    issuer: str | None = None
    state_cookie_domain: str | None = None


@dataclass
class _AuthCfg:
    casdoor: _CasdoorCfg = field(default_factory=_CasdoorCfg)


@dataclass
class _AppCfg:
    auth: _AuthCfg = field(default_factory=_AuthCfg)


def _make_app() -> FastAPI:
    from extensions.auth.routes import router as auth_router

    app = FastAPI()
    app.include_router(auth_router)
    return app


@pytest.fixture()
def app() -> FastAPI:
    return _make_app()


@pytest.fixture()
def client(app: FastAPI):
    with TestClient(app) as c:
        yield c


def _self_signed_key_and_cert_pem() -> tuple[object, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "casdoor-test")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
        .not_valid_after(datetime.now(UTC) + timedelta(hours=1))
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    return key, cert_pem


class TestCasdoorAuth:
    def test_enabled_endpoint(self, client: TestClient):
        with patch("extensions.auth.routes.get_app_config", return_value=_AppCfg()):
            res = client.get("/api/auth/casdoor/enabled")
        assert res.status_code == 200
        assert res.json() == {"enabled": True}

    def test_login_redirect_sets_state_cookie(self, client: TestClient):
        with patch("extensions.auth.routes.get_app_config", return_value=_AppCfg()):
            res = client.get("/api/auth/casdoor/login", follow_redirects=False)
        assert res.status_code == 302
        assert res.headers["location"].startswith("https://casdoor.example.com/login/oauth/authorize?")
        # state stored in cookie
        assert "deerflow_casdoor_state=" in res.headers.get("set-cookie", "")

    def test_callback_issues_deerflow_token_and_redirects(self, client: TestClient):
        cfg = _AppCfg()
        state = "state-abc"
        id_tok = "header.payload.sig"

        class _TokenResult:
            access_token = "access.jwt.token"
            id_token = id_tok

        with (
            patch("extensions.auth.routes.get_app_config", return_value=cfg),
            patch("extensions.auth.routes.exchange_code_for_tokens", return_value=_TokenResult()),
            patch("extensions.auth.routes.verify_casdoor_jwt", return_value={"sub": "u1"}),
            patch("extensions.auth.routes.get_account", return_value={"name": "u1", "email": "a@b.com"}),
            patch("extensions.auth.routes.find_or_create_user", return_value={"id": "00000000-0000-0000-0000-000000000001", "username": "a"}),
        ):
            res = client.get(
                "/api/auth/casdoor/callback?code=abc&state=state-abc",
                headers={"Cookie": f"deerflow_casdoor_state={state}"},
                follow_redirects=False,
            )
        assert res.status_code == 302
        assert res.headers["location"].startswith("/login?token=")
        assert f"token={id_tok}" in res.headers["location"]

    def test_logout_accepts_casdoor_jwt_when_deerflow_decode_fails(self, client: TestClient):
        cfg = _AppCfg()
        with (
            patch("extensions.auth.routes.get_app_config", return_value=cfg),
            patch("extensions.auth.routes.decode_token", return_value=None),
            patch("extensions.auth.routes.verify_casdoor_jwt", return_value={"sub": "x"}),
        ):
            res = client.post("/api/auth/logout", headers={"Authorization": "Bearer any.jwt"})
        assert res.status_code == 200
        assert res.json().get("message")

    def test_refresh_allowed_with_casdoor_enabled(self, app: FastAPI):
        uid = uuid4()

        def _user() -> CurrentUser:
            return CurrentUser(
                {
                    "id": uid,
                    "username": "u",
                    "email": "u@example.com",
                    "is_superuser": False,
                    "organization_id": None,
                    "department_id": None,
                    "data_permission_level": "self",
                    "is_active": True,
                },
                [],
                [],
            )

        app.dependency_overrides[get_current_user] = _user
        cfg = _AppCfg()
        try:
            with (
                TestClient(app) as client,
                patch("extensions.auth.routes.get_app_config", return_value=cfg),
                patch("extensions.auth.routes.verify_casdoor_jwt", return_value={"sub": "u1"}),
            ):
                res = client.post("/api/auth/refresh", headers={"Authorization": "Bearer x"})
            assert res.status_code == 403
            assert res.json().get("detail") == "Token refresh is not available when using Casdoor JWT"
        finally:
            app.dependency_overrides.clear()


class TestVerifyCasdoorJwt:
    def test_accepts_valid_rs256_jwt(self) -> None:
        key, cert_pem = _self_signed_key_and_cert_pem()
        cfg = CasdoorConfig(
            enabled=True,
            endpoint="https://casdoor.example.com",
            client_id="test-client",
            client_secret="x",
            certificate=cert_pem,
        )
        now = datetime.now(UTC)
        tok = pyjwt.encode(
            {
                "sub": "user-1",
                "aud": "test-client",
                "iss": "https://casdoor.example.com",
                "exp": now + timedelta(hours=1),
            },
            key,
            algorithm="RS256",
        )
        claims = verify_casdoor_jwt(tok, cfg)
        assert claims is not None
        assert claims.get("sub") == "user-1"

    def test_rejects_wrong_audience(self) -> None:
        key, cert_pem = _self_signed_key_and_cert_pem()
        cfg = CasdoorConfig(
            enabled=True,
            endpoint="https://casdoor.example.com",
            client_id="test-client",
            client_secret="x",
            certificate=cert_pem,
        )
        now = datetime.now(UTC)
        tok = pyjwt.encode(
            {
                "sub": "user-1",
                "aud": "other-client",
                "iss": "https://casdoor.example.com",
                "exp": now + timedelta(hours=1),
            },
            key,
            algorithm="RS256",
        )
        claims = verify_casdoor_jwt(tok, cfg)
        assert claims is not None
        assert claims.get("sub") == "user-1"
