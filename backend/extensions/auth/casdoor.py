"""Casdoor OAuth helpers (authorize URL, token exchange, get-account).

This module intentionally keeps network logic isolated from FastAPI routes.
"""

from __future__ import annotations

import secrets
import ssl
import tempfile
import time
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx
import jwt
from cryptography import x509
from jwt import PyJWTError

if TYPE_CHECKING:
    from deerflow.config.app_config import CasdoorConfig

import logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CasdoorTokenResult:
    access_token: str | None
    id_token: str | None
    token_type: str | None
    raw: dict[str, Any]


def new_state() -> str:
    return secrets.token_urlsafe(24)


def build_authorize_url(
    *,
    endpoint: str,
    client_id: str,
    redirect_uri: str,
    state: str,
    scope: str = "openid profile email",
    response_type: str = "code",
) -> str:
    base = endpoint.rstrip("/")
    url = f"{base}/login/oauth/authorize"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": response_type,
        "scope": scope,
        "state": state,
    }
    return f"{url}?{urllib.parse.urlencode(params)}"


def _ssl_context_from_certificate(certificate_pem: str | None) -> ssl.SSLContext | None:
    """Build SSL context with the provided CA certificate.

    When certificate_pem is not provided, return None to use system defaults.
    """
    cert = (certificate_pem or "").strip()
    if not cert:
        return None
    ctx = ssl.create_default_context()
    # httpx supports passing an SSLContext.
    with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=True) as f:
        f.write(cert)
        f.flush()
        ctx.load_verify_locations(f.name)
    return ctx


async def exchange_code_for_tokens(
    *,
    endpoint: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code: str,
    certificate_pem: str | None = None,
    timeout_seconds: float = 10.0,
) -> CasdoorTokenResult:
    """Exchange authorization code for tokens.

    Casdoor implements an OAuth2 token endpoint at /api/login/oauth/access_token.
    """
    base = endpoint.rstrip("/")
    url = f"{base}/api/login/oauth/access_token"
    data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
    }
    verify = _ssl_context_from_certificate(certificate_pem)
    async with httpx.AsyncClient(timeout=timeout_seconds, verify=verify) as client:
        res = await client.post(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        res.raise_for_status()
        payload = res.json()
    return CasdoorTokenResult(
        access_token=payload.get("access_token"),
        id_token=payload.get("id_token"),
        token_type=payload.get("token_type"),
        raw=payload,
    )


async def get_account(
    *,
    endpoint: str,
    access_token: str,
    certificate_pem: str | None = None,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    """Fetch Casdoor user info via /api/get-account."""
    base = endpoint.rstrip("/")
    url = f"{base}/api/get-account"
    verify = _ssl_context_from_certificate(certificate_pem)
    async with httpx.AsyncClient(timeout=timeout_seconds, verify=verify) as client:
        res = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
        res.raise_for_status()
        return res.json()


def _public_key_from_certificate_pem(pem: str) -> Any:
    cert = x509.load_pem_x509_certificate(pem.strip().encode())
    return cert.public_key()


def verify_casdoor_jwt(token: str, cfg: CasdoorConfig) -> dict[str, Any] | None:
    """Decode Casdoor JWT without signature verification.

    This is intended for scenarios where only user identity extraction is needed.
    """
    try:
        return jwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_exp": False,
                "verify_aud": False,
                "verify_iss": False,
            },
            algorithms=["RS256", "HS256"],
        )
    except PyJWTError as e:
        logger.warning("Casdoor JWT decode error: %s", e)
        return None


def pick_identity(claims: Mapping[str, Any]) -> tuple[str, str | None, str | None]:
    """Return (username, email, real_name) from Casdoor account payload with fallbacks."""
    email = (claims.get("email") or "").strip() or None
    name = (claims.get("name") or "").strip() or None
    display_name = (claims.get("displayName") or claims.get("display_name") or "").strip() or None
    sub = (claims.get("sub") or claims.get("id") or "").strip() or None

    # Prefer stable identifiers to avoid collisions / renames.
    if sub:
        username = f"casdoor_{sub}"
    else:
        username = name or email or f"user_{int(time.time())}"
    username = username.replace("@", "_")
    real_name = display_name or name or None
    return username, email, real_name
