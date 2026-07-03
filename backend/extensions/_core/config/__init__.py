"""Config loader and compat for extensions (ENV, search engine, etc.)."""

from extensions._core.config.loader import (
    get_bool_env,
    get_str_env,
    load_yaml_config,
)
from extensions._core.config.tools_compat import (
    SELECTED_SEARCH_ENGINE,
    SearchEngine,
)

__all__ = [
    "load_yaml_config",
    "get_str_env",
    "get_bool_env",
    "SearchEngine",
    "SELECTED_SEARCH_ENGINE",
]
