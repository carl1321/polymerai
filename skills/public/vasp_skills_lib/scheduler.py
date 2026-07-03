"""JobScheduler — single-threaded event loop for N independent HPC jobs.

Used by multi-job skills (vasp-phonon, vasp-elastic manual, vasp-defect,
vasp-batch). Replaces the per-disp ``for sub in subs: run_with_handlers(...)``
pattern that serialized 42 phonon disps into 84-hour wall clock chains.

Design contract:
  - Each task = a ``(work_dir, build_script_callable)`` pair.
  - Scheduler keeps at most ``max_concurrent`` jobs RUNNING at once.
  - Polls all running jobs once per loop iteration; terminal jobs trigger
    fetch + custodian check; if a correction is applied the task is
    re-enqueued (attempt += 1) up to ``max_errors`` times.
  - Persists state to ``state_file`` after every loop iteration.
  - On SIGINT, saves state and returns; remote jobs are NOT cancelled.
  - On startup, ``resume()`` reads ``state_file`` and re-attaches to any
    still-RUNNING / PENDING job by job_id without re-submitting.

Concurrency model: single Python thread, no locks. The remote scheduler
(Slurm / SCNet) provides actual parallelism.
"""

from __future__ import annotations

import json
import signal
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from .executor.base import Executor, JobHandle, JobState, OPEN_STATES, TERMINAL_STATES
from .handlers import default_bundle
from .runtime import RuntimeState, append_event, write_progress


STATE_FILE_VERSION = 1


def _handle_to_dict(h: JobHandle | None) -> dict[str, Any] | None:
    if h is None:
        return None
    return {
        "job_id": h.job_id,
        "backend": h.backend,
        "remote_work_dir": h.remote_work_dir,
        "submitted_at": h.submitted_at,
        "extra": h.extra,
    }


def _handle_from_dict(d: dict[str, Any] | None) -> JobHandle | None:
    if not d:
        return None
    return JobHandle(
        job_id=d["job_id"],
        backend=d["backend"],
        remote_work_dir=d["remote_work_dir"],
        submitted_at=float(d.get("submitted_at") or 0),
        extra=d.get("extra") or {},
    )


@dataclass
class _Task:
    work_dir: Path
    build_script: Callable[[], str] = field(repr=False)
    job_name: str = "vasp"
    state: str = "pending"        # pending / running / done / failed
    attempt: int = 0
    handle: JobHandle | None = None
    on_done: Callable[[Path, bool, dict], None] | None = field(default=None, repr=False)
    error: str | None = None

    def to_persist(self) -> dict[str, Any]:
        return {
            "work_dir": str(self.work_dir),
            "job_name": self.job_name,
            "state": self.state,
            "attempt": self.attempt,
            "handle": _handle_to_dict(self.handle),
            "error": self.error,
        }


class JobScheduler:
    def __init__(
        self,
        executor: Executor,
        *,
        state_file: Path,
        max_concurrent: int = 8,
        poll_interval: int = 60,
        max_errors: int = 5,
        use_handlers: bool = True,
    ):
        self.executor = executor
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.max_concurrent = max(1, max_concurrent)
        self.poll_interval = max(1, poll_interval)
        self.max_errors = max_errors
        self.use_handlers = use_handlers
        self._tasks: list[_Task] = []
        self._stopped = False
        self._signal_installed = False

    # ---------------------------------------------------------- API
    def add(self, work_dir: Path, build_script: Callable[[], str], *,
            job_name: str = "vasp",
            on_done: Callable[[Path, bool, dict], None] | None = None) -> None:
        """Register a task. ``build_script`` is called lazily, including after
        each correction so updated INCAR/POTCAR are picked up on resubmit."""
        existing = self._find_by_work_dir(work_dir)
        if existing is not None:
            existing.build_script = build_script
            existing.on_done = on_done
            existing.job_name = job_name
            return
        self._tasks.append(_Task(
            work_dir=Path(work_dir),
            build_script=build_script,
            job_name=job_name,
            on_done=on_done,
        ))

    def submit_all(self) -> dict[str, Any]:
        """Enqueue every pending task once (no poll / sleep). Uses a burst slot cap."""
        saved = self.max_concurrent
        self.max_concurrent = max(len(self._tasks), 1)
        limit = max(len(self._tasks), 1) * max(self.max_errors, 1) + 10
        for _ in range(limit):
            if not self._has_pending():
                break
            self._launch_pending()
        self.max_concurrent = saved
        self._persist()
        return self.summary()

    def tick(self) -> dict[str, Any]:
        """Single scheduler iteration: poll running jobs, fill free slots, persist (no sleep)."""
        self._poll_running()
        self._launch_pending()
        self._persist()
        return self.summary()

    def run(self) -> dict[str, Any]:
        """Drive the loop until all tasks reach a terminal state.

        Returns a summary dict.
        """
        self._install_signal_handler()
        try:
            while not self._stopped:
                self._launch_pending()
                running = [t for t in self._tasks if t.state == "running"]
                if not running and not self._has_pending():
                    break
                if not running and self._has_pending():
                    # Pending tasks waiting for a slot; should not happen
                    # because _launch_pending fills slots up to max_concurrent.
                    time.sleep(1)
                    continue
                time.sleep(self.poll_interval)
                self._poll_running()
                self._persist()
        finally:
            self._persist()
        return self.summary()

    def summary(self) -> dict[str, Any]:
        done = [t for t in self._tasks if t.state == "done"]
        failed = [t for t in self._tasks if t.state == "failed"]
        return {
            "total": len(self._tasks),
            "completed": len(done),
            "failed": len(failed),
            "completed_dirs": [str(t.work_dir) for t in done],
            "failed_dirs": [str(t.work_dir) for t in failed],
            "success": len(failed) == 0 and len(done) == len(self._tasks),
        }

    # ---------------------------------------------------- internals
    def _has_pending(self) -> bool:
        return any(t.state == "pending" for t in self._tasks)

    def _find_by_work_dir(self, work_dir: Path) -> _Task | None:
        target = str(Path(work_dir))
        for t in self._tasks:
            if str(t.work_dir) == target:
                return t
        return None

    def _launch_pending(self) -> None:
        running_count = sum(1 for t in self._tasks if t.state == "running")
        for t in self._tasks:
            if self._stopped:
                break
            if t.state != "pending":
                continue
            if running_count >= self.max_concurrent:
                break
            self._enqueue(t)
            if t.state == "running":
                running_count += 1

    def _enqueue(self, task: _Task) -> None:
        task.attempt += 1
        try:
            script = task.build_script()
        except Exception as e:
            task.state = "failed"
            task.error = f"build_script failed: {e}"
            self._record_terminal(task, success=False, info={"error": task.error})
            return
        write_progress(task.work_dir, {
            "state": RuntimeState.QUEUED,
            "attempt": task.attempt,
        })
        try:
            handle = self.executor.enqueue(task.work_dir, script, job_name=task.job_name)
        except Exception as e:
            task.error = f"enqueue failed: {e}"
            append_event(task.work_dir, {"event": "enqueue_failed", "attempt": task.attempt, "error": str(e)})
            if task.attempt >= self.max_errors:
                task.state = "failed"
                self._record_terminal(task, success=False, info={"error": task.error})
            # else: leave as pending so next loop retries
            return
        task.handle = handle
        task.state = "running"
        append_event(task.work_dir, {
            "event": "job_submitted",
            "attempt": task.attempt,
            "job_id": handle.job_id,
            "remote_work_dir": handle.remote_work_dir,
        })
        from .runtime import write_job
        write_job(task.work_dir, {
            "backend": handle.backend,
            "attempt": task.attempt,
            "job_id": handle.job_id,
            "remote_work_dir": handle.remote_work_dir,
        })
        write_progress(task.work_dir, {
            "state": RuntimeState.RUNNING,
            "attempt": task.attempt,
        })

    def _poll_running(self) -> None:
        for t in self._tasks:
            if t.state != "running" or t.handle is None:
                continue
            try:
                state = self.executor.poll(t.handle)
            except Exception as e:
                append_event(t.work_dir, {"event": "poll_failed", "error": str(e)})
                continue
            if state in OPEN_STATES:
                continue
            self._on_terminal(t, state)

    def _on_terminal(self, task: _Task, state: str) -> None:
        handle = task.handle
        assert handle is not None
        # fetch results
        try:
            self.executor.fetch(handle.remote_work_dir, task.work_dir, patterns=None)
        except Exception as e:
            append_event(task.work_dir, {"event": "fetch_failed", "error": str(e)})
        append_event(task.work_dir, {
            "event": "attempt_finished",
            "attempt": task.attempt,
            "job_id": handle.job_id,
            "state": state,
        })
        # Custodian-style correction (single-threaded, safe)
        if self.use_handlers and state != JobState.COMPLETED and task.attempt < self.max_errors:
            corrected = False
            try:
                bundle = default_bundle(task.work_dir)
                import os as _os
                old = _os.getcwd()
                try:
                    _os.chdir(task.work_dir)
                    corrected, msgs = bundle.check_and_correct()
                finally:
                    _os.chdir(old)
                for msg in msgs:
                    append_event(task.work_dir, {
                        "event": "correction_applied",
                        "attempt": task.attempt,
                        "message": msg,
                    })
            except Exception as e:
                append_event(task.work_dir, {"event": "handler_failed", "error": str(e)})
            if corrected:
                task.state = "pending"
                task.handle = None
                write_progress(task.work_dir, {"state": RuntimeState.CORRECTING})
                return
        success = state == JobState.COMPLETED
        task.state = "done" if success else "failed"
        if not success:
            task.error = f"job ended in state {state}"
        self._record_terminal(task, success=success, info={"state": state})

    def _record_terminal(self, task: _Task, *, success: bool, info: dict[str, Any]) -> None:
        write_progress(task.work_dir, {
            "state": RuntimeState.FINISHED if success else RuntimeState.FAILED,
            "attempt": task.attempt,
            "completed": success,
        })
        append_event(task.work_dir, {
            "event": "task_finished",
            "success": success,
            "attempt": task.attempt,
            **info,
        })
        if task.on_done is not None:
            try:
                task.on_done(task.work_dir, success, info)
            except Exception as e:
                append_event(task.work_dir, {"event": "on_done_failed", "error": str(e)})

    # -------------------------------------------------- persistence
    def _persist(self) -> None:
        payload = {
            "version": STATE_FILE_VERSION,
            "tasks": [t.to_persist() for t in self._tasks],
        }
        tmp = self.state_file.with_suffix(self.state_file.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.state_file)

    def restore(self, *, build_scripts: dict[str, Callable[[], str]],
                on_dones: dict[str, Callable[[Path, bool, dict], None]] | None = None) -> None:
        """Re-attach to running jobs from the state file. Pass the same
        ``build_scripts`` map the caller would pass to ``add()`` so corrections
        can re-submit. ``on_dones`` is optional, keyed by str(work_dir)."""
        if not self.state_file.exists():
            return
        try:
            payload = json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception:
            return
        on_dones = on_dones or {}
        for raw in payload.get("tasks", []):
            wd = Path(raw["work_dir"])
            key = str(wd)
            build = build_scripts.get(key)
            if build is None:
                # Caller did not register this task; skip
                continue
            t = _Task(
                work_dir=wd,
                build_script=build,
                job_name=raw.get("job_name", "vasp"),
                state=raw.get("state", "pending"),
                attempt=int(raw.get("attempt", 0)),
                handle=_handle_from_dict(raw.get("handle")),
                on_done=on_dones.get(key),
                error=raw.get("error"),
            )
            # If saved state was 'running' but handle missing, demote to pending
            if t.state == "running" and t.handle is None:
                t.state = "pending"
                t.attempt = max(0, t.attempt - 1)
            existing = self._find_by_work_dir(wd)
            if existing is not None:
                # Caller already added this work_dir; merge persisted handle/state
                existing.state = t.state
                existing.attempt = t.attempt
                existing.handle = t.handle
                existing.error = t.error
            else:
                self._tasks.append(t)

    # ----------------------------------------------------- signals
    def _install_signal_handler(self) -> None:
        if self._signal_installed:
            return
        self._signal_installed = True

        def _handler(signum, frame):
            print("\n[scheduler] received signal — saving state and exiting", flush=True)
            self._stopped = True

        try:
            signal.signal(signal.SIGINT, _handler)
        except Exception:
            pass
