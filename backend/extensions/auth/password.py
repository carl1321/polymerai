"""Password hashing and verification (bcrypt with plain fallback for dev)."""

import logging

logger = logging.getLogger(__name__)

try:
    import bcrypt
except ImportError:
    bcrypt = None
    logger.warning("bcrypt not installed. Using INSECURE plain-text fallback. Install bcrypt for production.")


def _plain_tag(password: str) -> str:
    return f"plain${password}"


def hash_password(password: str) -> str:
    """Hash password with bcrypt or plain fallback."""
    if bcrypt is not None:
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")
    return _plain_tag(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against stored hash."""
    if password_hash.startswith("plain$"):
        return password_hash == _plain_tag(password)
    if bcrypt is None:
        logger.error("bcrypt not installed but hash is not plain$ format.")
        return False
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except Exception as e:
        logger.error("Error verifying password: %s", e)
        return False
