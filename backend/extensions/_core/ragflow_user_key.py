"""Login-time RAGFlow per-user API key: fetch from external service and store in users.ragflow_key."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote
from uuid import UUID

import requests
import yaml

from deerflow.config.app_config import AppConfig
from extensions.auth.db import UserDB

logger = logging.getLogger(__name__)


def _load_ragflow_yaml_section() -> dict[str, Any]:
    try:
        path = AppConfig.resolve_config_path(None)
    except FileNotFoundError:
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning("ragflow_user_key: failed to read config: %s", e)
        return {}
    return config.get("ragflow") or {}


def get_user_api_key_fetch_settings() -> tuple[str | None, dict[str, str]]:
    """Return (base_url for GET, extra headers). Request uses ?username=."""
    raw = _load_ragflow_yaml_section()
    base = (raw.get("user_api_key_fetch_url") or "").strip()
    headers: dict[str, str] = {}
    extra = raw.get("user_api_key_fetch_headers")
    if isinstance(extra, dict):
        for k, v in extra.items():
            if isinstance(k, str) and isinstance(v, str) and v.strip():
                headers[k] = v.strip()
    return (base or None), headers


def parse_api_key_from_fetch_response(resp: requests.Response) -> str | None:
    if resp.status_code != 200:
        logger.warning(
            "ragflow_user_key fetch: status=%s body=%s",
            resp.status_code,
            (resp.text or "")[:300],
        )
        return None
    ct = (resp.headers.get("Content-Type") or "").lower()
    text = (resp.text or "").strip()
    if not text:
        return None
    if "json" in ct or text.startswith("{"):
        try:
            data = resp.json()
        except Exception:
            data = None
        if isinstance(data, dict):
            key = data.get("api_key")
            if isinstance(key, str) and key.strip():
                return key.strip()
            inner = data.get("data")
            if isinstance(inner, str) and inner.strip():
                return inner.strip()
            if isinstance(inner, dict):
                key2 = inner.get("api_key")
                if isinstance(key2, str) and key2.strip():
                    return key2.strip()
        return None
    return text


def normalize_username_for_ragflow(username: str) -> str:
    """Normalize local username for rfkey lookup.

    Current rule: if username contains '@', keep only the local-part.
    Example: 'zhangxw@szlab.ac.cn' -> 'zhangxw'
    """
    raw = (username or "").strip()
    if "@" in raw:
        local = raw.split("@", 1)[0].strip()
        return local or raw
    return raw


def fetch_ragflow_key_for_username(username: str, base_url: str, headers: dict[str, str]) -> str | None:
    normalized = normalize_username_for_ragflow(username)
    sep = "&" if "?" in base_url else "?"
    url = f"{base_url}{sep}username={quote(normalized, safe='')}"
    try:
        resp = requests.get(url, headers=headers or None, timeout=15)
    except Exception as e:
        logger.warning("ragflow_user_key fetch request failed: %s", e)
        return None
    return parse_api_key_from_fetch_response(resp)


def ensure_user_ragflow_key(user_row: dict[str, Any], username: str) -> None:
    """If users.ragflow_key is empty, GET fetch URL and UPDATE user row."""
    if (user_row.get("ragflow_key") or "").strip():
        return
    base, headers = get_user_api_key_fetch_settings()
    if not base:
        return
    key = fetch_ragflow_key_for_username(username.strip(), base, headers)
    if not key:
        return
    raw_id = user_row.get("id")
    if raw_id is None:
        return
    user_id = raw_id if isinstance(raw_id, UUID) else UUID(str(raw_id))
    try:
        UserDB.update_user(user_id, ragflow_key=key)
        logger.info("ragflow_key stored for user_id=%s", user_id)
    except Exception as e:
        logger.warning("ragflow_key store failed for user_id=%s: %s", user_id, e)
