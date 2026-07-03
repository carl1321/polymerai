"""JWT token creation and verification."""

import logging
import os
from datetime import datetime, timedelta
from typing import Any

import jwt
from jwt import PyJWTError

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("JWT_SECRET_KEY", os.getenv("DEER_FLOW_JWT_SECRET", "change-me-in-production"))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))


def create_access_token(
    user_id: str,
    username: str,
    is_superuser: bool = False,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token."""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "username": username,
        "is_superuser": is_superuser,
        "jti": __import__("uuid").uuid4().hex,
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any] | None:
    """Decode and verify JWT; return payload or None."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except PyJWTError as e:
        logger.warning("JWT decode error: %s", e)
        return None
    except Exception as e:
        logger.error("Unexpected error decoding token: %s", e)
        return None


def get_token_jti(token: str) -> str | None:
    """Extract JTI from token for blacklist."""
    payload = decode_token(token)
    return payload.get("jti") if payload else None
