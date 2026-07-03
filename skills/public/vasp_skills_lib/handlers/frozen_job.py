"""Frozen-job detector: flags VASP runs whose output has stopped advancing."""

from __future__ import annotations

import time
from pathlib import Path


class FrozenJobHandler:
    """Detect stalled VASP jobs by checking log-file modification time.

    This is a lightweight complement to custodian's FrozenJobErrorHandler.
    It does NOT patch INCAR — it only reports the stall so the runner can
    decide whether to kill/resubmit.
    """

    def __init__(self, work_dir: Path, stale_seconds: int = 900):
        self.work_dir = Path(work_dir)
        self.stale_seconds = stale_seconds
        self._detected = False

    def check(self) -> bool:
        self._detected = False
        for name in ("vasp.out", "OSZICAR", "OUTCAR"):
            path = self.work_dir / name
            if not path.exists():
                continue
            age = time.time() - path.stat().st_mtime
            if age < self.stale_seconds:
                return False
            if path.stat().st_size == 0:
                continue
            self._detected = True
            return True
        return False

    def correct(self) -> dict:
        return {
            "detected": ["frozen_job"] if self._detected else [],
            "applied": [
                {
                    "error": "frozen_job",
                    "severity": "high",
                    "fix": f"output files unchanged for >{self.stale_seconds}s",
                    "actions": ["kill_and_resubmit"],
                }
            ]
            if self._detected
            else [],
        }
