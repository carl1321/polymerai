"""Minimal stub for RAG/tools config used by retriever. Export SELECTED_RAG_PROVIDER."""

import os

from extensions._core.config.loader import load_yaml_config

def _get_rag_provider() -> str:
    config = load_yaml_config()
    env_config = config.get("ENV") or {}
    return env_config.get("RAG_PROVIDER") or os.getenv("RAG_PROVIDER", "rag_flow")

SELECTED_RAG_PROVIDER = _get_rag_provider()
