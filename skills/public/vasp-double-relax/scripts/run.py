#!/usr/bin/env python3
"""vasp-double-relax CLI — two-stage relaxation (stage1 submit + DeerFlow poll for stage2)."""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import sys
from pathlib import Path

from pymatgen.core import Structure

from vasp_skills_lib import load_config
from vasp_skills_lib.inputs.sets import build_relax_inputs
from vasp_skills_lib.potcar import generate_potcar
from vasp_skills_lib.runner import (
    build_submit_script,
    emit_deerflow_async_envelope,
    resolve_vasp_command,
    submit_job_only,
)
from vasp_skills_lib.runtime import append_event, write_progress


def _setup_potcar(stage_dir: Path, user_potcar: Path | None, config, dry_run: bool) -> None:
    if user_potcar is not None:
        shutil.copy2(user_potcar, stage_dir / "POTCAR")
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


def _write_stage2_dry(structure, stage2_dir: Path, args, config) -> None:
    overrides2 = {
        "ISIF": args.isif,
        "IBRION": 1,
        "EDIFFG": args.stage2_ediffg,
        "NSW": args.stage2_nsw,
    }
    build_relax_inputs(
        structure,
        stage2_dir,
        user_incar=args.incar,
        user_kpoints=args.kpoints,
        incar_overrides=overrides2,
    )
    _setup_potcar(stage2_dir, args.potcar, config, True)


def _poll_command(work: Path, config_path: Path | None) -> str:
    poll_py = "/mnt/skills/public/vasp-double-relax/scripts/poll.py"
    parts = ["python", poll_py, "--work-dir", shlex.quote(str(work.resolve()))]
    if config_path is not None:
        parts.extend(["--config", shlex.quote(str(config_path.resolve()))])
    return " ".join(parts)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="vasp-double-relax")
    p.add_argument("poscar", type=Path)
    p.add_argument("--work-dir", type=Path, default=Path("./double_relax"))
    p.add_argument("--incar", type=Path, default=None)
    p.add_argument("--kpoints", type=Path, default=None)
    p.add_argument("--potcar", type=Path, default=None)
    p.add_argument("--input-dir", type=Path, default=None)
    p.add_argument("--executor", choices=["local", "ssh", "scnet"], default=None)
    p.add_argument("--config", type=Path, default=None)
    p.add_argument("--isif", type=int, default=3)
    p.add_argument("--stage1-ediffg", type=float, default=-0.05)
    p.add_argument("--stage1-nsw", type=int, default=200)
    p.add_argument("--stage2-ediffg", type=float, default=-0.01)
    p.add_argument("--stage2-nsw", type=int, default=300)
    p.add_argument("--stage2-encut-boost", type=float, default=1.3)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-handlers", action="store_true", help="Ignored (detached submit only).")
    p.add_argument("--max-errors", type=int, default=5, help="Ignored (detached submit only).")
    p.add_argument("--poll-interval-seconds", type=int, default=1800)
    p.add_argument("--first-poll-delay-seconds", type=int, default=30)
    args = p.parse_args(argv)

    if not args.poscar.exists():
        print(f"ERROR: POSCAR not found: {args.poscar}", file=sys.stderr)
        return 1

    config = load_config(args.config)
    work = args.work_dir
    work.mkdir(parents=True, exist_ok=True)
    structure = Structure.from_file(str(args.poscar))

    stage1_dir = work / "stage1"
    stage2_dir = work / "stage2"

    write_progress(work, {"software": "vasp", "calc_type": "double-relax", "state": "running"})

    overrides1 = {"ISIF": args.isif, "IBRION": 2, "EDIFFG": args.stage1_ediffg, "NSW": args.stage1_nsw}
    build_relax_inputs(
        structure,
        stage1_dir,
        user_incar=args.incar,
        user_kpoints=args.kpoints,
        incar_overrides=overrides1,
    )
    _setup_potcar(stage1_dir, args.potcar, config, args.dry_run)

    if args.dry_run:
        print(f"DRY RUN: stage1 inputs in {stage1_dir}")
        _write_stage2_dry(structure, stage2_dir, args, config)
        return 0

    append_event(work, {"event": "stage1_started"})
    cmd = resolve_vasp_command(config, args.executor)
    submit = build_submit_script(config, executor_override=args.executor, job_name="drelax-s1")
    last = submit_job_only(
        stage1_dir,
        cmd,
        config,
        executor_override=args.executor,
        submit_script=submit,
        job_name="drelax-s1",
    )

    rt = work / ".calc_runtime"
    rt.mkdir(parents=True, exist_ok=True)
    meta = {
        "isif": args.isif,
        "stage1_ediffg": args.stage1_ediffg,
        "stage1_nsw": args.stage1_nsw,
        "stage2_ediffg": args.stage2_ediffg,
        "stage2_nsw": args.stage2_nsw,
        "stage2_encut_boost": args.stage2_encut_boost,
        "incar": str(args.incar) if args.incar else None,
        "kpoints": str(args.kpoints) if args.kpoints else None,
        "input_dir": str(args.input_dir) if args.input_dir else None,
        "potcar": str(args.potcar) if args.potcar else None,
        "executor": args.executor,
    }
    (rt / "double_relax_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    (rt / "double_relax_state.json").write_text(json.dumps({"stage": 1}, indent=2), encoding="utf-8")

    emit_deerflow_async_envelope(
        work_dir=work,
        config_path=args.config,
        job_id=last.job_id,
        task_kind="vasp_double_relax",
        display_name=args.poscar.stem or "vasp-double-relax",
        poll_interval_seconds=args.poll_interval_seconds,
        first_poll_delay_seconds=args.first_poll_delay_seconds,
        poll_command=_poll_command(work, args.config),
    )
    stub = {
        "submitted": True,
        "work_dir": str(work.resolve()),
        "task_kind": "vasp_double_relax",
        "external_ref": last.job_id or "",
        "note": "Two-stage relax; scripts/poll.py advances to stage2 then writes summary.json.",
    }
    print(json.dumps(stub, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
