"""Local executor: subprocess in the work_dir, optional background submit."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

from .base import Executor, ExecutionResult, JobHandle, JobState


class LocalExecutor(Executor):
    def __init__(self, vasp_cmd: str = "vasp_std", **_):
        self.vasp_cmd = vasp_cmd
        # Track background processes by pid (string) so JobHandle is JSON-friendly
        self._procs: dict[str, subprocess.Popen] = {}

    # ------------------------------------------------------------------ run
    def run(self, work_dir: Path, command: str, timeout: int | None = None) -> ExecutionResult:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return ExecutionResult(proc.returncode, proc.stdout, proc.stderr)

    # -------------------------------------------------------- detached API
    def enqueue(self, work_dir: Path, submit_script: str, job_name: str = "vasp") -> JobHandle:
        script_path = work_dir / "submit.sh"
        script_path.write_text(submit_script.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
        # Spawn in background so enqueue is non-blocking
        out_log = open(work_dir / "vasp.out", "ab")
        err_log = open(work_dir / "stderr.txt", "ab")
        proc = subprocess.Popen(
            ["bash", script_path.name],
            cwd=str(work_dir),
            stdout=out_log,
            stderr=err_log,
            start_new_session=os.name != "nt",
        )
        self._procs[str(proc.pid)] = proc
        return JobHandle(
            job_id=str(proc.pid),
            backend="local",
            remote_work_dir=str(work_dir.resolve()),
            submitted_at=time.time(),
        )

    def poll(self, handle: JobHandle) -> str:
        proc = self._procs.get(handle.job_id)
        if proc is not None:
            rc = proc.poll()
            if rc is None:
                return JobState.RUNNING
            return JobState.COMPLETED if rc == 0 else JobState.FAILED
        try:
            pid = int(handle.job_id)
        except ValueError:
            return JobState.UNKNOWN
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            ok = self._infer_local_success(handle)
            return JobState.COMPLETED if ok else JobState.FAILED
        except PermissionError:
            return JobState.UNKNOWN
        return JobState.RUNNING

    def _infer_local_success(self, handle: JobHandle) -> bool:
        wd = Path(handle.remote_work_dir or "")
        out = wd / "vasp.out"
        if not out.exists():
            return False
        try:
            tail = out.read_text(encoding="utf-8", errors="replace")[-8000:]
        except OSError:
            return False
        return "General timing" in tail or "reached required accuracy" in tail

    def fetch(self, remote_work_dir: str, local_work_dir: Path,
              patterns: list[str] | None = None) -> None:
        return None  # local — files already in place

    def cancel(self, handle: JobHandle) -> None:
        proc = self._procs.get(handle.job_id)
        if proc is None or proc.poll() is not None:
            return
        try:
            if os.name == "nt":
                proc.terminate()
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            pass

    def _read_remote_stdout(self, handle: JobHandle, work_dir: Path) -> str:
        out = work_dir / "vasp.out"
        if out.exists():
            try:
                return out.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass
        return ""
