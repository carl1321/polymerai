#!/usr/bin/env python3
"""vasp-relax CLI — prepare inputs, submit HPC/local job (always non-blocking + DeerFlow async envelope)."""

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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vasp-relax", description="VASP structure relaxation")
    p.add_argument("poscar", type=Path, help="Input POSCAR (or structure file pymatgen accepts)")
    p.add_argument("--work-dir", type=Path, default=Path("./relax"))
    p.add_argument("--incar", type=Path, default=None, help="User-supplied INCAR")
    p.add_argument("--kpoints", type=Path, default=None)
    p.add_argument("--potcar", type=Path, default=None, help="User-supplied POTCAR (skip auto-gen)")
    p.add_argument("--input-dir", type=Path, default=None, help="Directory with pre-built INCAR/KPOINTS")
    p.add_argument(
        "--executor",
        choices=["local", "ssh", "scnet"],
        default=None,
        help="Override config executor. `local` is disabled unless VASP_SKILLS_ALLOW_LOCAL=1 (default: HPC only).",
    )
    p.add_argument("--config", type=Path, default=None)
    p.add_argument("--isif", type=int, default=3)
    p.add_argument("--ibrion", type=int, default=2)
    p.add_argument("--ediffg", type=float, default=-0.02)
    p.add_argument("--nsw", type=int, default=100)
    p.add_argument("--encut", type=float, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-handlers", action="store_true", help="Ignored (non-blocking submit only).")
    p.add_argument("--max-errors", type=int, default=5, help="Ignored (non-blocking submit only).")
    p.add_argument(
        "--poll-interval-seconds",
        type=int,
        default=300,
        help="Hint for DeerFlow async_tasks row (gateway poll cadence). Default 300s.",
    )
    p.add_argument(
        "--first-poll-delay-seconds",
        type=int,
        default=15,
        help="Seconds before first background poll (envelope first_poll_delay_seconds).",
    )
    p.add_argument("--wait", action="store_true", help=argparse.SUPPRESS)
    return p


def _relax_poll_command(work_dir: Path, config_path: Path | None) -> str:
    poll_py = "/mnt/skills/public/vasp-relax/scripts/poll.py"
    parts = ["python", poll_py, "--work-dir", shlex.quote(str(work_dir.resolve()))]
    if config_path is not None:
        parts.extend(["--config", shlex.quote(str(config_path.resolve()))])
    return " ".join(parts)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.wait:
        print(
            "ERROR: --wait is not supported. Use detached submit only (no --wait); "
            "DeerFlow async_tasks + gateway poll track the job.",
            file=sys.stderr,
        )
        return 2
    if not args.poscar.exists():
        print(f"ERROR: POSCAR not found: {args.poscar}", file=sys.stderr)
        return 1

    config = load_config(args.config)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    structure = Structure.from_file(str(args.poscar))

    overrides = {
        "ISIF": args.isif,
        "IBRION": args.ibrion,
        "EDIFFG": args.ediffg,
        "NSW": args.nsw,
    }
    if args.encut is not None:
        overrides["ENCUT"] = args.encut

    user_incar = args.incar
    user_kpoints = args.kpoints
    if args.input_dir:
        from vasp_skills_lib.inputs.sets import resolve_input_files

        user_incar, user_kpoints = resolve_input_files(
            args.work_dir,
            user_incar=user_incar,
            user_kpoints=user_kpoints,
            input_dir=args.input_dir,
        )

    build_relax_inputs(
        structure,
        args.work_dir,
        user_incar=user_incar,
        user_kpoints=user_kpoints,
        incar_overrides=overrides,
    )

    if args.potcar is not None:
        shutil.copy2(args.potcar, args.work_dir / "POTCAR")
    else:
        try:
            generate_potcar(
                poscar=args.work_dir / "POSCAR",
                work_dir=args.work_dir,
                functional=config.potcar.get("functional", "PBE"),
                backend=config.potcar.get("backend", "vasp-potcar"),
            )
        except Exception as e:
            print(f"WARN: POTCAR generation failed ({e}). Provide --potcar.", file=sys.stderr)
            if not args.dry_run:
                return 1

    if args.dry_run:
        print(f"DRY RUN: inputs prepared in {args.work_dir}", file=sys.stderr)
        return 0

    command = resolve_vasp_command(config, args.executor)
    submit_script = build_submit_script(config, executor_override=args.executor, job_name="vasp-relax")
    if not submit_script:
        print("ERROR: could not build submit script for executor", file=sys.stderr)
        return 1

    display_stem = args.poscar.stem or "vasp-relax"

    print(
        f"[vasp-relax] Submitting detached job (work_dir={args.work_dir.resolve()}). "
        "Use scripts/poll.py or DeerFlow async_tasks gateway poll.",
        file=sys.stderr,
        flush=True,
    )
    try:
        last = submit_job_only(
            args.work_dir,
            command,
            config,
            executor_override=args.executor,
            submit_script=submit_script,
            job_name="vasp-relax",
        )
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    emit_deerflow_async_envelope(
        work_dir=args.work_dir,
        config_path=args.config,
        job_id=last.job_id,
        task_kind="vasp_relax",
        display_name=display_stem,
        poll_interval_seconds=args.poll_interval_seconds,
        first_poll_delay_seconds=args.first_poll_delay_seconds,
        poll_command=_relax_poll_command(args.work_dir, args.config),
    )
    stub = {
        "submitted": True,
        "work_dir": str(args.work_dir.resolve()),
        "task_kind": "vasp_relax",
        "external_ref": last.job_id or "",
        "note": "Job running remotely; parse_relax/summary.json available after poll completes.",
    }
    print(json.dumps(stub, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
