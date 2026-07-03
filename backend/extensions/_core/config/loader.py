"""Compat layer for agentic_workflow tools: load config as dict (ENV, IMAGE_GEN, etc.)."""

import os
from typing import Any

import yaml

from deerflow.config.app_config import AppConfig

_config_cache: dict | None = None


def load_yaml_config(filename: str | None = None) -> dict:
    """Load config YAML as dict. Uses deer-flow config.yaml path; ignores filename."""
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    path = AppConfig.resolve_config_path(None)
    with open(path, encoding="utf-8") as f:
        _config_cache = yaml.safe_load(f) or {}
    return _config_cache


def _get_config_value(key_path: str, default: Any = None) -> Any:
    """Get value from config by dot path, e.g. ENV.MP_API_KEY."""
    config = load_yaml_config()
    keys = key_path.split(".")
    value: Any = config
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    return value


def get_str_env(name: str, default: str = "") -> str:
    """Get string from os.environ or config ENV section."""
    val = os.getenv(name)
    if val is not None:
        return str(val).strip()
    yaml_val = _get_config_value(f"ENV.{name}", None)
    if yaml_val is not None:
        return str(yaml_val).strip()
    return default


def get_bool_env(name: str, default: bool = False) -> bool:
    """Get bool from os.environ or config ENV section."""
    val = os.getenv(name)
    if val is not None:
        return str(val).strip().lower() in ("1", "true", "yes", "y", "on")
    yaml_val = _get_config_value(f"ENV.{name}", None)
    if yaml_val is not None:
        if isinstance(yaml_val, bool):
            return yaml_val
        return str(yaml_val).strip().lower() in ("1", "true", "yes", "y", "on")
    return default


def get_int_env(name: str, default: int = 0) -> int:
    """Get int from os.environ or config ENV section."""
    val = os.getenv(name)
    if val is not None:
        try:
            return int(val)
        except ValueError:
            return default
    yaml_val = _get_config_value(f"ENV.{name}", None)
    if yaml_val is not None:
        try:
            return int(yaml_val)
        except (ValueError, TypeError):
            return default
    return default
