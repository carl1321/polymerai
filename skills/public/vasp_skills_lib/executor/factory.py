"""Build an Executor from a Config."""

from __future__ import annotations

from ..config import Config
from .base import Executor
from .enforce_remote import assert_remote_executor_or_explicit_local
from .local import LocalExecutor
from .ssh import SSHExecutor
from .scnet import SCNetExecutor


def get_executor(config: Config, override: str | None = None) -> Executor:
    assert_remote_executor_or_explicit_local(config, override)
    kind = override or config.executor
    if kind == "local":
        return LocalExecutor(**config.local)
    if kind == "ssh":
        return SSHExecutor(**config.ssh)
    if kind == "scnet":
        return SCNetExecutor(**config.scnet)
    raise ValueError(f"Unknown executor: {kind}")
