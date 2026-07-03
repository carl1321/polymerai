"""Compat for agentic_workflow tools: SearchEngine, SELECTED_SEARCH_ENGINE, load_yaml_config."""

import enum
import os

from extensions._core.config.loader import load_yaml_config

__all__ = ["SearchEngine", "SELECTED_SEARCH_ENGINE", "load_yaml_config"]


class SearchEngine(enum.Enum):
    TAVILY = "tavily"
    DUCKDUCKGO = "duckduckgo"
    BRAVE_SEARCH = "brave_search"
    ARXIV = "arxiv"
    SEARX = "searx"
    WIKIPEDIA = "wikipedia"


def _get_search_engine() -> str:
    config = load_yaml_config()
    env_config = config.get("ENV") or {}
    return env_config.get("SEARCH_API") or os.getenv("SEARCH_API", SearchEngine.TAVILY.value)


SELECTED_SEARCH_ENGINE = _get_search_engine()
