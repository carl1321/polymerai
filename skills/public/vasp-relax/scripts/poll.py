#!/usr/bin/env python3
"""Poll a detached vasp-relax job (submit via run.py default async path).

Emits **one line JSON** on stdout for the DeerFlow ``async_tasks`` dispatcher.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from vasp_skills_lib import load_config
from vasp_skills_lib.executor import get_executor
from vasp_skills_lib.executor.base import JobHandle, JobState
from vasp_skills_lib.parsing import parse_relax
from vasp_skills_lib.runtime import RuntimeState, append_event, read_job, write_progress


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Poll detached vasp-relax job")
    p.add_argument("--work-dir", type=Path, required=True)
    p.add_argument("--config", type=Path, default=None)
    args = p.parse_args(argv)
    work_dir = args.work_dir.resolve()
    cfg = load_config(args.config)
    job = read_job(work_dir)
    jid = job.get("job_id")
    if not jid:
        _emit({"status": "failed", "error": {"message": "missing job_id in .calc_runtime/job.json"}})
        return 1
    backend = str(job.get("backend") or cfg.executor)
    if backend not in {"local", "ssh", "scnet"}:
        backend = cfg.executor
    rwd = job.get("remote_work_dir")

    handle = JobHandle(
        job_id=str(jid),
        backend=backend,
        remote_work_dir=str(rwd) if rwd else "",
    )
    try:
        ex_override = backend if backend in {"local", "ssh", "scnet"} else None
        with get_executor(cfg, ex_override) as ex:
            state = ex.poll(handle)
            if state == JobState.COMPLETED:
                rw = str(rwd or "")
                if rw and backend in {"ssh", "scnet"}:
                    ex.fetch(rw, work_dir, patterns=None)
                    if not (work_dir / "vasprun.xml").exists():
                        _emit(
                            {
                                "status": "failed",
                                "error": {
                                    "message": (
                                        "Scheduler reported COMPLETED but vasprun.xml is missing "
                                        f"after fetch from {backend} ({rw}). "
                                        "Check remote job logs, walltime, and SFTP/API permissions."
                                    ),
                                },
                            }
                        )
                        write_progress(work_dir, {"state": RuntimeState.FAILED})
                        append_event(
                            work_dir,
                            {"event": "poll_fetch_empty", "job_id": str(jid), "remote_work_dir": rw},
                        )
                        return 1
    except Exception as e:
        _emit({"status": "failed", "error": {"message": str(e)}})
        return 1

    if state in (JobState.PENDING, JobState.RUNNING, JobState.UNKNOWN):
        _emit({"status": "running", "job_state": state})
        return 0

    if state == JobState.CANCELLED:
        _emit({"status": "cancelled"})
        write_progress(work_dir, {"state": RuntimeState.FAILED, "cancelled": True})
        append_event(work_dir, {"event": "poll_cancelled", "job_id": str(jid)})
        return 0

    if state == JobState.FAILED:
        _emit({"status": "failed", "error": {"message": "Remote scheduler reported FAILED"}})
        write_progress(work_dir, {"state": RuntimeState.FAILED})
        append_event(work_dir, {"event": "poll_failed", "job_id": str(jid)})
        return 0

    try:
        result = parse_relax(work_dir)
    except Exception as e:
        _emit({"status": "failed", "error": {"message": f"parse_relax failed: {e}"}})
        write_progress(work_dir, {"state": RuntimeState.FAILED})
        append_event(work_dir, {"event": "poll_parse_error", "job_id": str(jid), "error": str(e)})
        return 1
    summary = {
        "converged": result.converged,
        "final_energy_eV": result.energy,
        "contcar": str(result.final_structure_path) if result.final_structure_path else None,
        "errors": result.errors or [],
    }
    (work_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    if result.errors:
        _emit({"status": "failed", "error": {"message": "; ".join(result.errors), "details": summary}})
        write_progress(work_dir, {"state": RuntimeState.FAILED})
    elif result.converged:
        _emit({"status": "completed", "result": summary})
        write_progress(work_dir, {"state": RuntimeState.FINISHED, "completed": True})
    else:
        _emit({"status": "failed", "error": {"message": "ionic relaxation did not converge", "details": summary}})
        write_progress(work_dir, {"state": RuntimeState.FAILED})
    append_event(work_dir, {"event": "poll_parsed", "job_id": str(jid), "summary": summary})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
