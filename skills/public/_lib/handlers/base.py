"""Error-handler base class.

A handler inspects a failed Gaussian `.log` and either proposes an input-file
mutation (to retry) or raises. Handlers are stateless; orchestration and retry
budgeting live in the skill's `scripts/run.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Fix:
    """A patch to apply to the next retry."""
    description: str
    new_keywords: list[str] | None = None      # keywords to append to Route
    drop_keywords: list[str] | None = None     # keywords to remove
    link0_patch: dict | None = None            # e.g. {"mem": "32GB"}
    use_last_geometry: bool = False            # reuse geometry from previous .log


class BaseHandler:
    """Override `detect` and `propose_fix`."""

    name: str = "base"

    def detect(self, log_text: str) -> bool:
        raise NotImplementedError

    def propose_fix(self, log_path: Path) -> Fix:
        raise NotImplementedError
