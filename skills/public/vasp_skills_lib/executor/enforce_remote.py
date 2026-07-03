"""Reject local executor unless explicitly allowed (org default: HPC only)."""

from __future__ import annotations

import os

from ..config import Config


def assert_remote_executor_or_explicit_local(
    config: Config, executor_override: str | None
) -> None:
    kind = (executor_override or config.executor or "").strip().lower()
    if kind != "local":
        return
    if os.environ.get("VASP_SKILLS_ALLOW_LOCAL", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return
    raise ValueError(
        "Local VASP executor is disabled: use --executor ssh|scnet or set "
        "executor to ssh/scnet in /mnt/skills/public/_shared-vasp/config.yaml. "
        "For developer-only local runs, export VASP_SKILLS_ALLOW_LOCAL=1."
    )
