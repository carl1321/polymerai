# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging
import os
from typing import Annotated, Optional

from langchain_core.tools import tool
from langchain_experimental.utilities import PythonREPL

from .decorators import log_io


def _is_python_repl_enabled() -> bool:
    """Check if Python REPL tool is enabled from configuration."""
    # Check environment variable first (takes precedence)
    env_enabled = os.getenv("ENABLE_PYTHON_REPL", "").lower()
    if env_enabled in ("true", "1", "yes", "on"):
        return True
    if env_enabled in ("false", "0", "no", "off"):
        return False

    # Use the same AppConfig source as the rest of DeerFlow (mtime-based reload),
    # not extensions._core.config.loader.load_yaml_config (separate process-wide cache
    # that never refreshes and can disagree with config.yaml after edits).
    try:
        from deerflow.config import get_app_config

        raw = get_app_config().model_dump()
        python_repl_config = raw.get("PYTHON_REPL") or {}
        if not isinstance(python_repl_config, dict):
            return True
        enabled = python_repl_config.get("enabled", True)
        if enabled is None:
            return True
        return bool(enabled)
    except Exception as e:
        logger.warning(f"Failed to read PYTHON_REPL from app config: {e}. Defaulting to enabled.")
        return True


# Initialize logger first
logger = logging.getLogger(__name__)

# REPL will be initialized lazily when needed
_repl_instance: Optional[PythonREPL] = None


def _get_repl() -> Optional[PythonREPL]:
    """Get or create REPL instance, checking enablement status."""
    global _repl_instance
    if _is_python_repl_enabled():
        if _repl_instance is None:
            _repl_instance = PythonREPL()
        return _repl_instance
    return None


@tool
@log_io
def python_repl_tool(
    code: Annotated[
        str, "The python code to execute to do further analysis or calculation."
    ],
):
    """Use this to execute python code and do data analysis or calculation. If you want to see the output of a value,
    you should print it out with `print(...)`. This is visible to the user."""

    # Check if the tool is enabled and get REPL instance
    repl = _get_repl()
    if repl is None:
        error_msg = (
            "Python REPL tool is disabled. Set PYTHON_REPL.enabled: true in config.yaml "
            "(or DEER_FLOW_CONFIG_PATH file), or set ENABLE_PYTHON_REPL=true. "
            "Restart the gateway after changing config if needed."
        )
        logger.warning(error_msg)
        return f"Tool disabled: {error_msg}"

    if not isinstance(code, str):
        error_msg = f"Invalid input: code must be a string, got {type(code)}"
        logger.error(error_msg)
        return f"Error executing code:\n```python\n{code}\n```\nError: {error_msg}"

    logger.info("Executing Python code")
    try:
        result = repl.run(code)
        # Check if the result is an error message by looking for typical error patterns
        if isinstance(result, str) and ("Error" in result or "Exception" in result):
            logger.error(result)
            return f"Error executing code:\n```python\n{code}\n```\nError: {result}"
        logger.info("Code execution successful")
    except BaseException as e:
        error_msg = repr(e)
        logger.error(error_msg)
        return f"Error executing code:\n```python\n{code}\n```\nError: {error_msg}"

    result_str = f"Successfully executed:\n```python\n{code}\n```\nStdout: {result}"
    return result_str
