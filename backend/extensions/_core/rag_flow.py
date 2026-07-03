"""RAGFlow API client: config and retrieval.

Used by gateway /api/rag and by lead_agent RAG tool.
Config: config.yaml ragflow.api_url, ragflow.api_key; optional env DEER_FLOW_RAGFLOW_API_URL, DEER_FLOW_RAGFLOW_API_KEY.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests
import yaml

from deerflow.config.app_config import AppConfig

logger = logging.getLogger(__name__)


def get_ragflow_config() -> dict[str, Any]:
    """Read ragflow section: api_url required; api_key may be empty (per-user key only)."""
    try:
        path = AppConfig.resolve_config_path(None)
    except FileNotFoundError as e:
        logger.debug("RAG: config path not found: %s", e)
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning("RAG: failed to read config from %s: %s", path, e)
        return {}
    out = config.get("ragflow") or {}
    api_url = (out.get("api_url") or os.environ.get("DEER_FLOW_RAGFLOW_API_URL") or "").strip().rstrip("/")
    api_key = (out.get("api_key") or os.environ.get("DEER_FLOW_RAGFLOW_API_KEY") or "").strip()
    if not api_url:
        return {}
    return {"api_url": api_url.rstrip("/"), "api_key": api_key}


def retrieve(
    question: str,
    dataset_ids: list[str],
    *,
    top_k: int = 10,
    similarity_threshold: float = 0.2,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve chunks from RAGFlow. Pass api_key to override config (e.g. users.ragflow_key)."""
    cfg = get_ragflow_config()
    if not cfg or not cfg.get("api_url"):
        logger.debug("RAG retrieve skipped: no ragflow api_url")
        return []
    if not dataset_ids:
        return []
    api_url = cfg["api_url"]
    eff_key = (api_key.strip() if api_key else "") or (cfg.get("api_key") or "")
    if not eff_key:
        logger.debug("RAG retrieve skipped: no api key")
        return []
    url = f"{api_url}/api/v1/retrieval"
    payload = {
        "question": question.strip(),
        "dataset_ids": dataset_ids,
        "top_k": top_k,
        "similarity_threshold": similarity_threshold,
    }
    try:
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {eff_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        if resp.status_code != 200:
            logger.warning(
                "RAGFlow retrieval failed: url=%s status=%s body=%s",
                url,
                resp.status_code,
                resp.text[:300],
            )
            return []
        data = resp.json()
        code = data.get("code") if isinstance(data, dict) else None
        if code is not None and code != 0:
            logger.warning(
                "RAGFlow retrieval code=%s message=%s",
                code,
                data.get("message", "")[:200],
            )
            return []
        inner = data.get("data") if isinstance(data, dict) else {}
        chunks = inner.get("chunks") if isinstance(inner, dict) else []
        if not isinstance(chunks, list):
            return []
        logger.info("RAG: retrieved %d chunk(s) for %d dataset(s)", len(chunks), len(dataset_ids))
        return chunks
    except Exception as e:
        logger.exception("RAGFlow retrieval request failed: %s", e)
        return []
