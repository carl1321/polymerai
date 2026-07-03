"""Executor abstraction: local, ssh, scnet. Returns (returncode, stdout, stderr)."""

from .base import Executor, ExecutionResult  # noqa: F401
from .factory import get_executor  # noqa: F401
