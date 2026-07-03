"""High-level runner: prepare inputs, invoke executor, loop on handlers."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .executor import get_executor
from .executor.base import ExecutionResult
from .handlers import default_bundle
from .runtime import (
    RuntimeState,
    append_event,
    history_dir,
    read_progress,
    write_job,
    write_progress,
)


@contextmanager
def _cwd(path: Path):
    old = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(old)


@dataclass
class RunOutcome:
    success: bool
    attempts: int
    last_result: ExecutionResult
    corrections: list[str]



def resolve_vasp_command(config: Config, executor_override: str | None = None) -> str:
    kind = executor_override or config.executor
    if kind == "local":
        return config.local.get("vasp_cmd", "mpirun -np 4 vasp_std") + " > vasp.out 2> stderr.txt"
    if kind == "ssh":
        return config.ssh.get("vasp_cmd", "mpirun vasp_std") + " > vasp.out 2> stderr.txt"
    if kind == "scnet":
        return config.scnet.get("vasp_cmd", "mpirun vasp_std") + " > vasp.out 2> stderr.txt"
    raise ValueError(f"Unknown executor: {kind}")



def build_submit_script(
    config: Config,
    executor_override: str | None = None,
    job_name: str = "vasp",
) -> str | None:
    """Return a scheduler submit script for remote executors, else None."""
    kind = executor_override or config.executor
    if kind == "local":
        vasp_cmd = config.local.get("vasp_cmd", "mpirun -np 4 vasp_std")
        return (
            "#!/bin/bash\n"
            f"{vasp_cmd} > vasp.out 2> stderr.txt\n"
        )
    remote = config.ssh if kind == "ssh" else config.scnet
    scheduler = remote.get("scheduler", "slurm")
    partition = remote.get("partition") or remote.get("queue", "normal")
    nodes = remote.get("nodes", 1)
    ntasks = remote.get("ntasks_per_node") or remote.get("cores", 32)
    walltime = remote.get("walltime", "24:00:00")
    vasp_cmd = remote.get("vasp_cmd", "mpirun vasp_std")
    modules = "\n".join(f"module load {m}" for m in (remote.get("modules") or []))
    if kind == "scnet":
        # SCNet portal wraps this in its own SLURM script and redirects job
        # stdout to vasp_<jobid>.out — but vasp-skills handlers parse vasp.out,
        # so we tee mpirun stdout into vasp.out + stderr into stderr.txt here.
        return (
            "#!/bin/bash\n"
            f"{modules}\n"
            f"{vasp_cmd} > vasp.out 2> stderr.txt\n"
        )
    if scheduler == "pbs":
        return (
            "#!/bin/bash\n"
            f"#PBS -N {job_name}\n"
            f"#PBS -q {partition}\n"
            f"#PBS -l nodes={nodes}:ppn={ntasks}\n"
            f"#PBS -l walltime={walltime}\n"
            "#PBS -o vasp.out\n"
            "#PBS -e stderr.txt\n"
            "cd $PBS_O_WORKDIR\n"
            f"{modules}\n"
            f"{vasp_cmd}\n"
        )
    if scheduler == "lsf":
        wall = walltime.rsplit(":", 1)[0] if walltime.count(":") == 2 else walltime
        return (
            "#!/bin/bash\n"
            f"#BSUB -J {job_name}\n"
            f"#BSUB -q {partition}\n"
            f"#BSUB -nnodes {nodes}\n"
            f"#BSUB -n {nodes * int(ntasks)}\n"
            f"#BSUB -W {wall}\n"
            "#BSUB -o vasp.out\n"
            "#BSUB -e stderr.txt\n"
            f"{modules}\n"
            f"{vasp_cmd}\n"
        )
    return (
        f"#!/bin/bash\n"
        f"#SBATCH -J {job_name}\n"
        f"#SBATCH -p {partition}\n"
        f"#SBATCH -N {nodes}\n"
        f"#SBATCH --ntasks-per-node={ntasks}\n"
        f"#SBATCH -t {walltime}\n"
        f"#SBATCH -o vasp.out\n"
        f"#SBATCH -e stderr.txt\n"
        f"\n{modules}\n{vasp_cmd}\n"
    )



def _persist_result_files(work_dir: Path, result: ExecutionResult) -> None:
    vasp_out = work_dir / "vasp.out"
    stderr_txt = work_dir / "stderr.txt"
    if not vasp_out.exists() and result.stdout:
        vasp_out.write_text(result.stdout, encoding="utf-8")
    if not stderr_txt.exists() and result.stderr:
        stderr_txt.write_text(result.stderr, encoding="utf-8")



def run_with_handlers(
    work_dir: Path,
    command: str,
    config: Config,
    executor_override: str | None = None,
    max_errors: int = 5,
    use_handlers: bool = True,
    submit_script: str | None = None,
) -> RunOutcome:
    """Run VASP with the shared error-handler correction loop."""
    corrections: list[str] = []
    attempt = 0
    last: ExecutionResult | None = None
    backend = executor_override or config.executor

    prior = read_progress(work_dir)
    write_progress(
        work_dir,
        {
            "software": "vasp",
            "backend": backend,
            "state": RuntimeState.QUEUED if submit_script else RuntimeState.RUNNING,
            "attempt": 0,
            "max_attempts": max_errors,
            "command": command,
            "started_at": prior.get("started_at"),
        },
    )
    append_event(work_dir, {"event": "run_started", "backend": backend, "submit": bool(submit_script)})

    try:
        with get_executor(config, executor_override) as ex:
            while attempt < max_errors:
                attempt += 1
                write_progress(
                    work_dir,
                    {
                        "state": RuntimeState.QUEUED if submit_script else RuntimeState.RUNNING,
                        "attempt": attempt,
                    },
                )
                append_event(work_dir, {"event": "attempt_started", "attempt": attempt})

                if submit_script:
                    last = ex.submit(work_dir, submit_script)
                else:
                    last = ex.run(work_dir, command)

                write_job(
                    work_dir,
                    {
                        "backend": backend,
                        "attempt": attempt,
                        "job_id": last.job_id,
                        "remote_work_dir": last.remote_work_dir,
                    },
                )
                if last.job_id:
                    append_event(
                        work_dir,
                        {
                            "event": "job_submitted",
                            "attempt": attempt,
                            "job_id": last.job_id,
                            "remote_work_dir": last.remote_work_dir,
                        },
                    )

                _persist_result_files(work_dir, last)
                _snapshot(work_dir, attempt)

                append_event(
                    work_dir,
                    {
                        "event": "attempt_finished",
                        "attempt": attempt,
                        "returncode": last.returncode,
                    },
                )

                if not use_handlers:
                    break

                bundle = default_bundle(work_dir)
                with _cwd(work_dir):
                    corrected, msgs = bundle.check_and_correct()
                corrections.extend(msgs)
                if not corrected:
                    break
                write_progress(work_dir, {"state": RuntimeState.CORRECTING, "attempt": attempt})
                for msg in msgs:
                    append_event(work_dir, {"event": "correction_applied", "attempt": attempt, "message": msg})

        success = last is not None and last.returncode == 0
        write_progress(
            work_dir,
            {
                "state": RuntimeState.FINISHED if success else RuntimeState.FAILED,
                "attempt": attempt,
                "completed": success,
            },
        )
        append_event(
            work_dir,
            {
                "event": "run_finished",
                "attempts": attempt,
                "success": success,
                "returncode": None if last is None else last.returncode,
            },
        )
        return RunOutcome(success=success, attempts=attempt, last_result=last, corrections=corrections)
    except Exception as e:
        write_progress(work_dir, {"state": RuntimeState.FAILED, "attempt": attempt, "error": str(e)})
        append_event(work_dir, {"event": "run_failed", "attempt": attempt, "error": str(e)})
        raise



def submit_job_only(
    work_dir: Path,
    command: str,
    config: Config,
    *,
    executor_override: str | None = None,
    submit_script: str,
    job_name: str = "vasp-relax",
) -> ExecutionResult:
    """Enqueue remote/local background job and return immediately (no poll/fetch/handler loop)."""
    backend = executor_override or config.executor
    prior = read_progress(work_dir)
    write_progress(
        work_dir,
        {
            "software": "vasp",
            "backend": backend,
            "state": RuntimeState.QUEUED,
            "attempt": 0,
            "max_attempts": 1,
            "command": command,
            "started_at": prior.get("started_at"),
            "detached": True,
        },
    )
    append_event(
        work_dir,
        {"event": "run_started", "backend": backend, "submit": True, "detached": True},
    )
    attempt = 1
    write_progress(work_dir, {"state": RuntimeState.QUEUED, "attempt": attempt})
    append_event(work_dir, {"event": "attempt_started", "attempt": attempt})
    with get_executor(config, executor_override) as ex:
        handle = ex.enqueue(work_dir, submit_script, job_name=job_name)
        last = ExecutionResult(0, "", "", remote_work_dir=handle.remote_work_dir, job_id=handle.job_id)
    write_job(
        work_dir,
        {
            "backend": backend,
            "attempt": attempt,
            "job_id": last.job_id,
            "remote_work_dir": last.remote_work_dir,
        },
    )
    if last.job_id:
        append_event(
            work_dir,
            {
                "event": "job_submitted",
                "attempt": attempt,
                "job_id": last.job_id,
                "remote_work_dir": last.remote_work_dir,
                "detached": True,
            },
        )
    _persist_result_files(work_dir, last)
    _snapshot(work_dir, attempt)
    append_event(
        work_dir,
        {"event": "submit_only_finished", "attempt": attempt, "job_id": last.job_id},
    )
    write_progress(
        work_dir,
        {
            "state": RuntimeState.RUNNING,
            "attempt": attempt,
            "pending_remote": True,
        },
    )
    return last


# DeerFlow gateway runs poll_command inside LocalSandbox `sh -c` without inheriting
# agent PYTHONPATH; skills live under /mnt/skills/public as package root for vasp_skills_lib.
_POLL_SANDBOX_PYTHONPATH = "/mnt/skills/public"


def _poll_command_with_sandbox_pythonpath(cmd: str) -> str:
    c = cmd.strip()
    if not c:
        return c
    if c.startswith("PYTHONPATH=") or f"PYTHONPATH={_POLL_SANDBOX_PYTHONPATH}" in c:
        return cmd
    return f"PYTHONPATH={_POLL_SANDBOX_PYTHONPATH} {cmd}"


def emit_deerflow_async_envelope(
    *,
    work_dir: Path,
    config_path: Path | None,
    job_id: str | None,
    task_kind: str,
    display_name: str,
    poll_interval_seconds: int = 1800,
    first_poll_delay_seconds: int = 30,
    poll_command: str | None = None,
) -> None:
    """Print DeerFlow async-task envelope as the **last** line of merged bash output (stderr).

    LocalSandbox concatenates stdout then stderr; stderr is last, so the envelope
    goes to stderr and must be the final print.
    """
    wd = shlex.quote(str(work_dir.resolve()))
    if poll_command is None:
        cfg_part = f" --config {shlex.quote(str(config_path.resolve()))}" if config_path is not None else ""
        poll_cmd = f"python -m vasp_skills_lib.detached_poll --work-dir {wd}{cfg_part}"
    else:
        poll_cmd = poll_command
    poll_cmd = _poll_command_with_sandbox_pythonpath(poll_cmd)
    env = {
        "status": "submitted",
        "task_kind": task_kind,
        "external_ref": job_id or "",
        "poll_interval_seconds": poll_interval_seconds,
        "poll_command": poll_cmd,
        "display_name": display_name,
        "first_poll_delay_seconds": first_poll_delay_seconds,
    }
    print(json.dumps(env, ensure_ascii=False), file=sys.stderr, flush=True)


def submit_and_emit_async(
    work_dir: Path,
    command: str,
    config: Config,
    *,
    executor_override: str | None,
    submit_script: str,
    job_name: str,
    task_kind: str,
    display_name: str,
    config_path: Path | None = None,
    poll_interval_seconds: int = 1800,
    first_poll_delay_seconds: int = 30,
    poll_command: str | None = None,
) -> ExecutionResult:
    """Enqueue VASP via ``submit_job_only`` and emit DeerFlow ``submitted`` envelope (non-blocking)."""
    last = submit_job_only(
        work_dir,
        command,
        config,
        executor_override=executor_override,
        submit_script=submit_script,
        job_name=job_name,
    )
    emit_deerflow_async_envelope(
        work_dir=work_dir,
        config_path=config_path,
        job_id=last.job_id,
        task_kind=task_kind,
        display_name=display_name,
        poll_interval_seconds=poll_interval_seconds,
        first_poll_delay_seconds=first_poll_delay_seconds,
        poll_command=poll_command,
    )
    return last


def _snapshot(work_dir: Path, attempt: int) -> None:
    history = history_dir(work_dir) / f"attempt_{attempt:02d}"
    history.mkdir(parents=True, exist_ok=True)
    for name in ("INCAR", "KPOINTS", "vasp.out", "stderr.txt"):
        f = work_dir / name
        if f.exists():
            shutil.copy2(f, history / name)
    (history / "attempt.json").write_text(json.dumps({"attempt": attempt}, indent=2), encoding="utf-8")
