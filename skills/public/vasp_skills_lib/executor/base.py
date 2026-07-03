"""Executor base class.

Two complementary APIs:

  Synchronous (single-job skills):
    - ``run(work_dir, command)``    : exec + capture, no scheduler
    - ``submit(work_dir, script)``  : enqueue + wait + fetch (composed default)

  Detached (scheduler / multi-job skills, PR-2/3):
    - ``enqueue(work_dir, script, job_name) → JobHandle``
    - ``poll(handle) → JobState``
    - ``fetch(remote_work_dir, local_work_dir, patterns)``
    - ``cancel(handle)``

The default ``submit()`` is implemented in this base class as
``enqueue + _wait_one + fetch`` so subclasses only need to provide the four
detached primitives plus optional ``run()``.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..runtime import append_event, write_progress


@dataclass
class ExecutionResult:
    returncode: int
    stdout: str
    stderr: str
    remote_work_dir: str | None = None
    job_id: str | None = None


@dataclass
class JobHandle:
    """All state needed to resume polling a remote job after a process restart."""
    job_id: str
    backend: str                      # "ssh" | "scnet" | "local"
    remote_work_dir: str
    submitted_at: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


class JobState:
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


OPEN_STATES = frozenset({JobState.PENDING, JobState.RUNNING, JobState.UNKNOWN})
TERMINAL_STATES = frozenset({JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED})


class Executor(ABC):
    # ------------------------------------------------------------------ run
    @abstractmethod
    def run(self, work_dir: Path, command: str, timeout: int | None = None) -> ExecutionResult:
        """Run ``command`` synchronously with cwd=work_dir.

        For remote executors, upload work_dir first. No scheduler involved.
        """

    # ----------------------------------------------------------- detached API
    @abstractmethod
    def enqueue(self, work_dir: Path, submit_script: str, job_name: str = "vasp") -> JobHandle:
        """Upload work_dir + submit a scheduler job (sbatch / qsub / SCNet POST).

        Returns immediately with a handle; does NOT wait for completion.
        """

    @abstractmethod
    def poll(self, handle: JobHandle) -> str:
        """Query current state. Returns one of JobState.* values."""

    @abstractmethod
    def fetch(self, remote_work_dir: str, local_work_dir: Path, patterns: list[str] | None = None) -> None:
        """Download files from remote_work_dir to local_work_dir.

        Pass an empty list / None to download everything.
        """

    def cancel(self, handle: JobHandle) -> None:
        """Best-effort cancel. Default no-op; subclasses override."""
        return None

    # -------------------------------------------------------- composed submit
    def submit(self, work_dir: Path, submit_script: str, *,
               poll_interval: int | None = None,
               job_name: str = "vasp") -> ExecutionResult:
        """Default ``submit()`` = enqueue + wait + fetch.

        Subclasses generally do not need to override this.
        """
        handle = self.enqueue(work_dir, submit_script, job_name=job_name)
        state = self._wait_one(handle, work_dir, poll_interval=poll_interval)
        self.fetch(handle.remote_work_dir, work_dir, patterns=None)
        rc = 0 if state == JobState.COMPLETED else 1
        stdout = self._read_remote_stdout(handle, work_dir)
        return ExecutionResult(
            rc,
            stdout,
            "",
            remote_work_dir=handle.remote_work_dir,
            job_id=handle.job_id,
        )

    # ------------------------------------------------------------ wait helper
    def _wait_one(self, handle: JobHandle, work_dir: Path, *,
                  poll_interval: int | None = None) -> str:
        """Adaptive poll loop. Shared between SSH / SCNet single-job paths."""
        init_interval, max_interval = self._initial_poll_interval(work_dir)
        if poll_interval is not None:
            init_interval = poll_interval
        interval = init_interval
        elapsed = 0
        long_wait_notified = False
        backend = handle.backend
        print(
            f"  [{backend}] Job {handle.job_id} submitted. "
            f"Poll interval: {interval}s → up to {max_interval}s.",
            flush=True,
        )
        while True:
            time.sleep(interval)
            elapsed += interval
            state = self.poll(handle)
            next_interval = min(int(interval * 1.5), max_interval)
            print(
                f"  [{backend}] Job {handle.job_id}: {state} "
                f"(elapsed ~{elapsed // 60}m, next poll in {next_interval}s)",
                flush=True,
            )
            if elapsed >= 300 and not long_wait_notified and state in OPEN_STATES:
                long_wait_notified = True
                print(
                    f"  [{backend}] Long-running job summary: "
                    f"job_id={handle.job_id}, state={state!r}, "
                    f"elapsed~{elapsed // 60}m, next_poll={next_interval}s, "
                    f"remote_work_dir={handle.remote_work_dir}. "
                    "The remote HPC job keeps running even if you close this conversation.",
                    flush=True,
                )
                append_event(work_dir, {
                    "event": "long_wait_notice",
                    "backend": backend,
                    "job_id": handle.job_id,
                    "state": state,
                    "elapsed_seconds": elapsed,
                    "next_poll_seconds": next_interval,
                    "remote_work_dir": handle.remote_work_dir,
                })
                write_progress(work_dir, {"long_wait_notified": True})
            if state in TERMINAL_STATES:
                return state
            interval = next_interval

    # ------------------------------------------------------- override hooks
    def _initial_poll_interval(self, work_dir: Path) -> tuple[int, int]:
        """Subclasses may override to pick adaptive intervals (e.g. SSH atom-count heuristic)."""
        return 60, 600

    def _read_remote_stdout(self, handle: JobHandle, work_dir: Path) -> str:
        """Subclasses may return stdout/vasp.out content for the legacy API result."""
        return ""

    # ---------------------------------------------------------- lifecycle
    def close(self) -> None:
        return None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
