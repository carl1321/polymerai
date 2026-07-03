"""RSA public key for client-side password encryption (optional)."""

import base64
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    from Crypto.Cipher import PKCS1_OAEP
    from Crypto.PublicKey import RSA
    from Crypto.Hash import SHA256

    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    PKCS1_OAEP = RSA = SHA256 = None

# Keys under backend/.keys so path is stable when running from backend or repo root
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
KEYS_DIR = _BACKEND_DIR / ".keys"
PRIVATE_KEY_PATH = KEYS_DIR / "rsa_private_key.pem"
PUBLIC_KEY_PATH = KEYS_DIR / "rsa_public_key.pem"
RSA_KEY_SIZE = 2048


def _ensure_keys_dir() -> None:
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(KEYS_DIR, 0o700)


def get_public_key() -> str:
    """Return RSA public key PEM for client encryption. Raises if pycryptodome not installed."""
    if not CRYPTO_AVAILABLE:
        raise RuntimeError("pycryptodome not installed. pip install pycryptodome for password encryption.")
    if PRIVATE_KEY_PATH.exists() and PUBLIC_KEY_PATH.exists():
        return PUBLIC_KEY_PATH.read_text(encoding="utf-8")
    key = RSA.generate(RSA_KEY_SIZE)
    private_pem = key.export_key("PEM").decode("utf-8")
    public_pem = key.publickey().export_key("PEM", pkcs=8).decode("utf-8")
    _ensure_keys_dir()
    PRIVATE_KEY_PATH.write_text(private_pem, encoding="utf-8")
    PUBLIC_KEY_PATH.write_text(public_pem, encoding="utf-8")
    if os.name != "nt":
        os.chmod(PRIVATE_KEY_PATH, 0o600)
    return public_pem


def decrypt_password(encrypted_password_b64: str) -> str | None:
    """Decrypt base64-encoded RSA-OAEP password. Returns None if crypto unavailable or decryption fails."""
    if not CRYPTO_AVAILABLE or not PRIVATE_KEY_PATH.exists():
        return None
    try:
        private_key = RSA.import_key(PRIVATE_KEY_PATH.read_text(encoding="utf-8"))
        cipher = PKCS1_OAEP.new(private_key, hashAlgo=SHA256)
        decrypted = cipher.decrypt(base64.b64decode(encrypted_password_b64))
        return decrypted.decode("utf-8")
    except Exception as e:
        logger.debug("Decrypt password failed: %s", e)
        return None
