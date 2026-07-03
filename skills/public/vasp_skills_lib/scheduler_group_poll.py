"""Single-tick poll for detached multi-job VASP flows (JobScheduler state file).

Emits one JSON line on stdout for DeerFlow ``async_tasks`` (no sleep in-process).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from vasp_skills_lib import load_config
from vasp_skills_lib.executor import get_executor
from vasp_skills_lib.parsing import parse_relax
from vasp_skills_lib.runtime import RuntimeState, append_event, read_progress, write_progress
from vasp_skills_lib.scheduler import JobScheduler


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _defect_finalize_mod():
    p = Path(__file__).resolve().parent.parent / "vasp-defect" / "scripts" / "run.py"
    spec = importlib.util.spec_from_file_location("vasp_defect_cli", p)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load vasp-defect run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _elastic_manual_summary(work_root: Path, meta: dict) -> dict:
    tags = meta.get("tags") or []
    rows: list[dict] = []
    for tag in tags:
        sub = work_root / tag
        try:
            pr = parse_relax(sub)
            rows.append(
                {
                    "tag": tag,
                    "success": pr.converged,
                    "energy_eV": pr.energy,
                    "converged": pr.converged,
                }
            )
        except Exception as e:
            rows.append({"tag": tag, "success": False, "error": str(e)})
    strain_ok = bool(rows) and all(r.get("success") for r in rows)
    return {
        "success": strain_ok,
        "finished": True,
        "work_dir": str(work_root.resolve()),
        "method": "manual",
        "strains": rows,
    }


def _phonon_run_summary(work_root: Path, meta: dict, sched_summary: dict) -> dict:
    expected = int(meta.get("expected_displacements") or 0)
    subs = sorted(p for p in work_root.iterdir() if p.is_dir() and p.name.startswith("disp-"))
    vaspruns = sum(1 for s in subs if (s / "vasprun.xml").exists())
    ok = bool(sched_summary.get("success")) and vaspruns == expected and expected > 0
    return {
        "success": ok,
        "finished": True,
        "work_dir": str(work_root.resolve()),
        "stage": "run",
        "success": ok,
        "expected_displacements": expected,
        "completed_displacements": vaspruns,
        "scheduler": sched_summary,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Poll JobScheduler detached group (one tick)")
    p.add_argument("--work-root", type=Path, required=True)
    p.add_argument("--state-file", type=Path, required=True)
    p.add_argument("--config", type=Path, default=None)
    args = p.parse_args(argv)
    work_root = args.work_root.resolve()
    meta_path = work_root / ".calc_runtime" / "detached_group.json"
    if not meta_path.exists():
        _emit({"status": "failed", "error": {"message": f"missing {meta_path}"}})
        return 1
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    kind = str(meta.get("kind") or "")
    cfg = load_config(args.config)
    entries = meta.get("entries") or []
    submit_script = meta.get("submit_script")
    if not entries or not submit_script:
        _emit({"status": "failed", "error": {"message": "detached_group.json needs entries and submit_script"}})
        return 1

    build_scripts: dict[str, object] = {}
    ss = str(submit_script)
    for e in entries:
        wd = str(Path(e["work_dir"]).resolve())
        build_scripts[wd] = (lambda s=ss: s)

    try:
        with get_executor(cfg, meta.get("executor")) as ex:
            sched = JobScheduler(
                ex,
                state_file=args.state_file.resolve(),
                max_concurrent=int(meta.get("max_concurrent", 8)),
                poll_interval=int(meta.get("poll_interval", 60)),
                max_errors=int(meta.get("max_errors", 5)),
                use_handlers=bool(meta.get("use_handlers", True)),
            )
            for e in entries:
                wd_path = Path(e["work_dir"]).resolve()
                sched.add(
                    wd_path,
                    build_scripts[str(wd_path)],
                    job_name=str(e.get("job_name") or "vasp"),
                )
            sched.restore(build_scripts=build_scripts, on_dones=None)
            tick_summary = sched.tick()
    except Exception as e:
        _emit({"status": "failed", "error": {"message": str(e)}})
        return 1

    total = tick_summary.get("total", 0)
    done_n = tick_summary.get("completed", 0) + tick_summary.get("failed", 0)
    if total and done_n < total:
        if kind == "phonon_run":
            prog = read_progress(work_root)
            write_progress(
                work_root,
                {
                    **prog,
                    "completed_displacements": tick_summary.get("completed", 0),
                    "state": RuntimeState.RUNNING,
                },
            )
        _emit({"status": "running", "jobs": tick_summary})
        return 0

    if not tick_summary.get("success"):
        _emit({"status": "failed", "error": {"message": "one or more scheduler tasks failed", "jobs": tick_summary}})
        write_progress(work_root, {"state": RuntimeState.FAILED})
        append_event(work_root, {"event": "group_poll_failed", "kind": kind, "jobs": tick_summary})
        return 0

    try:
        if kind == "defect":
            mod = _defect_finalize_mod()
            summary = mod.defect_detached_finalize(work_root, meta)
            summary["success"] = bool(tick_summary.get("success"))
        elif kind == "elastic_manual":
            summary = _elastic_manual_summary(work_root, meta)
        elif kind == "phonon_run":
            summary = _phonon_run_summary(work_root, meta, tick_summary)
        else:
            _emit({"status": "failed", "error": {"message": f"unknown kind {kind!r}"}})
            return 1
    except Exception as e:
        _emit({"status": "failed", "error": {"message": str(e)}})
        return 1

    (work_root / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _emit({"status": "completed", "result": summary})
    write_progress(work_root, {"state": RuntimeState.FINISHED, "completed": True})
    append_event(work_root, {"event": "group_poll_completed", "kind": kind})
    return 0


if __name__ == "__main__":
    sys.exit(main())
