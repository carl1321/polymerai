"""Poll a detached VASP job (submit via ``submit_job_only`` + DeerFlow envelope).

Emits **one line JSON** on stdout for the DeerFlow ``async_tasks`` dispatcher.
Unlike ``vasp-relax/scripts/poll.py``, this does **not** run relax-specific parsing;
on scheduler COMPLETED it only records a minimal ``summary.json`` and reports completed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from vasp_skills_lib import load_config
from vasp_skills_lib.executor import get_executor
from vasp_skills_lib.executor.base import JobHandle, JobState
from vasp_skills_lib.runtime import RuntimeState, append_event, read_job, write_progress


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Poll detached VASP job (generic)")
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
    except Exception as e:
        _emit({"status": "failed", "error": {"message": str(e)}})
        return 1

    if state in (JobState.PENDING, JobState.RUNNING, JobState.UNKNOWN):
        _emit({"status": "running", "job_state": str(state)})
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

    summary = {"finished": True, "work_dir": str(work_dir)}
    (work_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _emit({"status": "completed", "result": summary})
    write_progress(work_dir, {"state": RuntimeState.FINISHED, "completed": True})
    append_event(work_dir, {"event": "poll_completed_generic", "job_id": str(jid), "summary": summary})
    return 0


if __name__ == "__main__":
    sys.exit(main())
