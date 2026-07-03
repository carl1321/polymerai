#!/usr/bin/env python3
"""Poll two-stage double relaxation: stage1 job → stage2 submit → stage2 job → summary."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from pymatgen.core import Structure
from pymatgen.io.vasp.inputs import Incar

from vasp_skills_lib import load_config
from vasp_skills_lib.executor import get_executor
from vasp_skills_lib.executor.base import OPEN_STATES, JobHandle, JobState
from vasp_skills_lib.inputs.sets import build_relax_inputs, resolve_input_files
from vasp_skills_lib.parsing import parse_relax
from vasp_skills_lib.potcar import generate_potcar
from vasp_skills_lib.runtime import RuntimeState, append_event, read_job, write_progress
from vasp_skills_lib.runner import build_submit_script, resolve_vasp_command, submit_job_only


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _state_path(work: Path) -> Path:
    return work / ".calc_runtime" / "double_relax_state.json"


def _meta_path(work: Path) -> Path:
    return work / ".calc_runtime" / "double_relax_meta.json"


def _setup_potcar(stage_dir: Path, user_potcar: str | None, config, dry_run: bool) -> None:
    if user_potcar:
        shutil.copy2(Path(user_potcar), stage_dir / "POTCAR")
    else:
        try:
            generate_potcar(
                stage_dir / "POSCAR",
                stage_dir,
                functional=config.potcar.get("functional", "PBE"),
                backend=config.potcar.get("backend", "vasp-potcar"),
            )
        except Exception as e:
            if not dry_run:
                print(f"WARN: POTCAR gen failed: {e}", file=sys.stderr)


def _build_summary(res1, res2, status: str) -> dict:
    summary: dict = {"status": status}
    summary["stage1"] = {
        "converged": res1.converged,
        "energy_eV": res1.energy,
    }
    if res2 is not None:
        summary["stage2"] = {
            "converged": res2.converged,
            "energy_eV": res2.energy,
            "contcar": str(res2.final_structure_path) if res2.final_structure_path else None,
        }
    return summary


def _poll_one(work_dir: Path, cfg, backend: str) -> tuple[str, object]:
    job = read_job(work_dir)
    jid = job.get("job_id")
    if not jid:
        return "failed", "missing job_id"
    rwd = job.get("remote_work_dir")
    handle = JobHandle(
        job_id=str(jid),
        backend=backend,
        remote_work_dir=str(rwd) if rwd else "",
    )
    ex_override = backend if backend in {"local", "ssh", "scnet"} else None
    with get_executor(cfg, ex_override) as ex:
        state = ex.poll(handle)
        if state == JobState.COMPLETED and rwd and backend in {"ssh", "scnet"}:
            ex.fetch(str(rwd), work_dir, patterns=None)
    return str(state), state


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="vasp-double-relax-poll")
    p.add_argument("--work-dir", type=Path, required=True)
    p.add_argument("--config", type=Path, default=None)
    args = p.parse_args(argv)
    work = args.work_dir.resolve()
    mp = _meta_path(work)
    if not mp.exists():
        _emit({"status": "failed", "error": {"message": f"missing {mp}"}})
        return 1
    meta = json.loads(mp.read_text(encoding="utf-8"))
    cfg = load_config(args.config)
    backend = str(meta.get("executor") or cfg.executor)
    if backend not in {"local", "ssh", "scnet"}:
        backend = cfg.executor

    stage1_dir = work / "stage1"
    stage2_dir = work / "stage2"
    sp = _state_path(work)
    st = {"stage": 1}
    if sp.exists():
        try:
            st = json.loads(sp.read_text(encoding="utf-8"))
        except Exception:
            pass
    stage = int(st.get("stage", 1))

    if stage == 1:
        try:
            js, state = _poll_one(stage1_dir, cfg, backend)
        except Exception as e:
            _emit({"status": "failed", "error": {"message": str(e)}})
            return 1
        if state in OPEN_STATES:
            _emit({"status": "running", "stage": 1, "job_state": js})
            return 0
        if state == JobState.CANCELLED:
            _emit({"status": "cancelled"})
            return 0
        if state != JobState.COMPLETED:
            _emit({"status": "failed", "error": {"message": f"stage1 ended {js}"}})
            return 0

        res1 = parse_relax(stage1_dir)
        contcar = stage1_dir / "CONTCAR"
        if not contcar.exists() or not res1.converged:
            summary = _build_summary(res1, None, "stage1_failed")
            (work / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
            _emit({"status": "failed", "error": {"message": "stage1 unconverged or missing CONTCAR", "summary": summary}})
            write_progress(work, {"state": RuntimeState.FAILED})
            return 0

        s2_structure = Structure.from_file(str(contcar))
        encut_boost = float(meta.get("stage2_encut_boost", 1.3))
        overrides2 = {
            "ISIF": int(meta.get("isif", 3)),
            "IBRION": 1,
            "EDIFFG": float(meta.get("stage2_ediffg", -0.01)),
            "NSW": int(meta.get("stage2_nsw", 300)),
        }
        if encut_boost > 1.0:
            s1_incar = Incar.from_file(str(stage1_dir / "INCAR"))
            if "ENCUT" in s1_incar:
                overrides2["ENCUT"] = int(s1_incar["ENCUT"] * encut_boost)

        user_incar = Path(meta["incar"]) if meta.get("incar") else None
        user_kpoints = Path(meta["kpoints"]) if meta.get("kpoints") else None
        input_dir = Path(meta["input_dir"]) if meta.get("input_dir") else None
        if input_dir:
            user_incar, user_kpoints = resolve_input_files(
                stage2_dir,
                user_incar=user_incar,
                user_kpoints=user_kpoints,
                input_dir=input_dir,
            )
        build_relax_inputs(
            s2_structure,
            stage2_dir,
            user_incar=user_incar,
            user_kpoints=user_kpoints,
            incar_overrides=overrides2,
        )
        _setup_potcar(stage2_dir, meta.get("potcar"), cfg, False)

        cmd = resolve_vasp_command(cfg, meta.get("executor"))
        submit2 = build_submit_script(cfg, executor_override=meta.get("executor"), job_name="drelax-s2")
        append_event(work, {"event": "stage2_started"})
        last = submit_job_only(
            stage2_dir,
            cmd,
            cfg,
            executor_override=meta.get("executor"),
            submit_script=submit2,
            job_name="drelax-s2",
        )
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps({"stage": 2, "stage2_job": last.job_id}, indent=2), encoding="utf-8")
        _emit({"status": "running", "stage": 2, "job_id": last.job_id or ""})
        return 0

    try:
        js, state = _poll_one(stage2_dir, cfg, backend)
    except Exception as e:
        _emit({"status": "failed", "error": {"message": str(e)}})
        return 1
    if state in OPEN_STATES:
        _emit({"status": "running", "stage": 2, "job_state": js})
        return 0
    if state == JobState.CANCELLED:
        _emit({"status": "cancelled"})
        return 0
    if state != JobState.COMPLETED:
        _emit({"status": "failed", "error": {"message": f"stage2 ended {js}"}})
        return 0

    res1 = parse_relax(stage1_dir)
    res2 = parse_relax(stage2_dir)
    status = "ok" if res2.converged else "stage2_unconverged"
    summary = _build_summary(res1, res2, status)
    summary["success"] = bool(res2.converged and status == "ok")
    (work / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_progress(work, {"state": RuntimeState.FINISHED if res2.converged else RuntimeState.FAILED})
    append_event(work, {"event": "stage2_finished", "converged": res2.converged})
    _emit({"status": "completed", "result": summary})
    return 0


if __name__ == "__main__":
    sys.exit(main())
