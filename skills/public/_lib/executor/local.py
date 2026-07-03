"""Local Gaussian executor.

Runs `g16` (or `g09`) directly on the current machine. Useful for dev/testing;
production HPC work goes through `ssh.py` or `scnet.py`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from dataclasses import dataclass


@dataclass
class LocalResult:
    returncode: int
    log_path: Path
    stdout: str
    stderr: str


class LocalExecutor:
    """Run Gaussian on the local machine.

    Requires `g16` or `g09` on PATH (overridable via `binary=`).
    """

    def __init__(self, binary: str | None = None, env: dict | None = None):
        if binary is None:
            binary = "g16" if shutil.which("g16") else ("g09" if shutil.which("g09") else "g16")
        self.binary = binary
        self.env = {**os.environ, **(env or {})}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, input_path: str | Path, work_dir: str | Path | None = None) -> LocalResult:
        input_path = Path(input_path).resolve()
        cwd = Path(work_dir).resolve() if work_dir else input_path.parent
        cwd.mkdir(parents=True, exist_ok=True)
        log_path = cwd / (input_path.stem + ".log")

        with log_path.open("wb") as logf:
            proc = subprocess.run(
                [self.binary, str(input_path)],
                cwd=cwd,
                env=self.env,
                stdout=logf,
                stderr=subprocess.PIPE,
            )
        return LocalResult(
            returncode=proc.returncode,
            log_path=log_path,
            stdout="",
            stderr=proc.stderr.decode("utf-8", errors="replace"),
        )
