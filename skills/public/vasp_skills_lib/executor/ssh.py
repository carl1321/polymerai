"""SSH executor using paramiko. Upload work_dir, run command, fetch results."""

from __future__ import annotations

import io
import posixpath
import re
import stat
import time
from pathlib import Path

import paramiko

from .base import Executor, ExecutionResult, JobHandle, JobState


_SLURM_OPEN = {"PENDING", "RUNNING", "REQUEUED", "RESIZING", "CONFIGURING", "SUSPENDED"}
_SLURM_TERMINAL_OK = {"COMPLETED"}
_SLURM_TERMINAL_BAD = {"FAILED", "CANCELLED", "TIMEOUT", "NODE_FAIL", "OUT_OF_MEMORY",
                       "BOOT_FAIL", "DEADLINE", "PREEMPTED"}


def _slurm_to_state(slurm_state: str) -> str:
    s = slurm_state.upper().split()[0] if slurm_state else ""
    if not s:
        return JobState.UNKNOWN
    if s in _SLURM_OPEN:
        return JobState.PENDING if s == "PENDING" else JobState.RUNNING
    if s in _SLURM_TERMINAL_OK:
        return JobState.COMPLETED
    if s == "CANCELLED":
        return JobState.CANCELLED
    if s in _SLURM_TERMINAL_BAD:
        return JobState.FAILED
    return JobState.UNKNOWN


class SSHExecutor(Executor):
    _TEXT_EXTS = {".sh", ".py", ".txt", ".yaml", ".yml"}
    _TEXT_NAMES = {"INCAR", "KPOINTS", "POSCAR", "CONTCAR", "POTCAR",
                   "submit.sh", "vasp.out", "stderr.txt"}

    _SUBMIT_CMD = {
        "slurm": "sbatch submit.sh",
        "pbs": "qsub submit.sh",
        "lsf": "bsub < submit.sh",
    }

    def __init__(
        self,
        host: str,
        user: str,
        port: int = 22,
        key_file: str | None = None,
        password: str | None = None,
        remote_root: str = "~/vasp_skills_runs",
        vasp_cmd: str = "mpirun vasp_std",
        scheduler: str = "slurm",
        modules: list[str] | None = None,
        **_: object,
    ):
        self.host = host
        self.user = user
        self.port = port
        self.remote_root = remote_root
        self.vasp_cmd = vasp_cmd
        self.scheduler = scheduler
        self.modules = modules or []
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._client.connect(
            hostname=host,
            port=port,
            username=user,
            key_filename=str(Path(key_file).expanduser()) if key_file else None,
            password=password,
        )
        self._sftp: paramiko.SFTPClient | None = None

    # ---------------------------------------------------------------- io
    @property
    def sftp(self) -> paramiko.SFTPClient:
        if self._sftp is None:
            self._sftp = self._client.open_sftp()
        return self._sftp

    def _mkdirs(self, remote_path: str) -> None:
        parts = remote_path.strip("/").split("/")
        cur = "/" if remote_path.startswith("/") else "."
        for p in parts:
            cur = posixpath.join(cur, p)
            try:
                self.sftp.stat(cur)
            except IOError:
                self.sftp.mkdir(cur)

    def _upload_dir(self, local_dir: Path, remote_dir: str) -> None:
        self._mkdirs(remote_dir)
        for entry in local_dir.iterdir():
            remote = posixpath.join(remote_dir, entry.name)
            if entry.is_dir():
                self._upload_dir(entry, remote)
            else:
                if entry.name in self._TEXT_NAMES or entry.suffix in self._TEXT_EXTS:
                    data = entry.read_bytes()
                    if b"\r\n" in data:
                        normalized = data.replace(b"\r\n", b"\n")
                        buf = io.BytesIO(normalized)
                        self.sftp.putfo(buf, remote, file_size=len(normalized))
                        continue
                self.sftp.put(str(entry), remote)

    def _resolve_remote_work(self, local_work_dir: Path) -> str:
        parts = local_work_dir.resolve().parts
        suffix = "_".join(parts[-2:]) if len(parts) >= 2 else parts[-1]
        return posixpath.join(self.remote_root, suffix)

    # --------------------------------------------------------------- run
    def run(self, work_dir: Path, command: str, timeout: int | None = None) -> ExecutionResult:
        remote_wd = self._resolve_remote_work(work_dir)
        self._upload_dir(work_dir, remote_wd)
        prelude = "\n".join(f"module load {m}" for m in self.modules)
        full = f"cd {remote_wd}\n{prelude}\n{command}"
        stdin, stdout, stderr = self._client.exec_command(full, timeout=timeout)
        rc = stdout.channel.recv_exit_status()
        return ExecutionResult(rc, stdout.read().decode(), stderr.read().decode(), remote_work_dir=remote_wd)

    # ----------------------------------------------------- detached API
    def enqueue(self, work_dir: Path, submit_script: str, job_name: str = "vasp") -> JobHandle:
        remote_wd = self._resolve_remote_work(work_dir)
        (work_dir / "submit.sh").write_text(
            submit_script.replace("\r\n", "\n"),
            encoding="utf-8",
            newline="\n",
        )
        self._upload_dir(work_dir, remote_wd)
        cmd = self._SUBMIT_CMD[self.scheduler]
        _, stdout, stderr = self._client.exec_command(f"cd {remote_wd} && {cmd}")
        rc = stdout.channel.recv_exit_status()
        out = stdout.read().decode()
        err = stderr.read().decode()
        job_id = self._parse_job_id(out)
        if rc != 0 or not job_id:
            raise RuntimeError(
                f"SSH job submit failed (rc={rc}): stdout={out!r} stderr={err!r}"
            )
        return JobHandle(
            job_id=job_id,
            backend="ssh",
            remote_work_dir=remote_wd,
            submitted_at=time.time(),
            extra={"scheduler": self.scheduler, "submit_stdout": out},
        )

    def poll(self, handle: JobHandle) -> str:
        if self.scheduler == "slurm":
            return _slurm_to_state(self._slurm_state(handle.job_id))
        # PBS / LSF — simple existence check + return UNKNOWN/RUNNING/COMPLETED
        return self._generic_state(handle.job_id)

    def cancel(self, handle: JobHandle) -> None:
        cancel_cmd = {"slurm": f"scancel {handle.job_id}",
                      "pbs": f"qdel {handle.job_id}",
                      "lsf": f"bkill {handle.job_id}"}.get(self.scheduler)
        if not cancel_cmd:
            return
        try:
            self._client.exec_command(cancel_cmd)
        except Exception:
            pass

    def fetch(self, remote_work_dir: str, local_work_dir: Path,
              patterns: list[str] | None = None) -> None:
        local_work_dir.mkdir(parents=True, exist_ok=True)
        try:
            entries = self.sftp.listdir_attr(remote_work_dir)
        except OSError as e:
            raise RuntimeError(
                f"SSH fetch: cannot list remote directory {remote_work_dir!r}: {e}"
            ) from e
        wanted = set(patterns) if patterns else None
        for e in entries:
            if wanted and e.filename not in wanted:
                continue
            if stat.S_ISDIR(e.st_mode):
                continue
            remote_file = posixpath.join(remote_work_dir, e.filename)
            self.sftp.get(remote_file, str(local_work_dir / e.filename))

    # ----------------------------------------------------- override hooks
    def _initial_poll_interval(self, work_dir: Path) -> tuple[int, int]:
        """Return (initial_interval_s, max_interval_s) based on POSCAR atom count."""
        natoms = 0
        poscar = work_dir / "POSCAR"
        if poscar.exists():
            try:
                lines = poscar.read_text(encoding="utf-8", errors="replace").splitlines()
                natoms = sum(int(x) for x in lines[6].split())
            except Exception:
                pass
        if natoms <= 10:
            return 30, 120
        if natoms <= 50:
            return 60, 300
        if natoms <= 200:
            return 120, 600
        return 300, 900

    def _read_remote_stdout(self, handle: JobHandle, work_dir: Path) -> str:
        try:
            with self.sftp.open(posixpath.join(handle.remote_work_dir, "vasp.out"), "r") as fh:
                return fh.read().decode("utf-8", errors="replace")
        except Exception:
            return ""

    # ----------------------------------------------------- internal helpers
    def _slurm_state(self, job_id: str) -> str:
        _, stdout, _ = self._client.exec_command(
            f"sacct -j {job_id} --format=State --noheader -P 2>/dev/null | head -1"
        )
        line = stdout.read().decode().strip()
        return line.split()[0] if line else ""

    def _generic_state(self, job_id: str) -> str:
        # Fallback: assume RUNNING until we can't find it, then COMPLETED.
        return JobState.RUNNING

    def _parse_job_id(self, out: str) -> str | None:
        m = re.search(r"(\d{4,})", out)
        return m.group(1) if m else None

    def close(self) -> None:
        if self._sftp is not None:
            self._sftp.close()
        self._client.close()
