#!/usr/bin/env python3
"""vasp-optics CLI — frequency-dependent ε(ω) via LOPTICS."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pymatgen.core import Structure

from vasp_skills_lib import load_config
from vasp_skills_lib.inputs.sets import build_optics_inputs, resolve_input_files
from vasp_skills_lib.potcar import generate_potcar
from vasp_skills_lib.runner import build_submit_script, resolve_vasp_command, submit_and_emit_async


def main() -> int:
    p = argparse.ArgumentParser(prog="vasp-optics")
    p.add_argument("poscar", type=Path)
    p.add_argument("--work-dir", type=Path, default=Path("./optics"))
    p.add_argument("--nbands-factor", type=float, default=3.0, help="multiply default NBANDS for many empty states")
    p.add_argument("--cshift", type=float, default=0.1, help="CSHIFT: Lorentzian broadening in eV")
    p.add_argument("--incar", type=Path, default=None)
    p.add_argument("--kpoints", type=Path, default=None)
    p.add_argument("--input-dir", type=Path, default=None)
    p.add_argument("--executor", choices=["local", "ssh", "scnet"], default=None)
    p.add_argument("--config", type=Path, default=None)
    p.add_argument("--potcar", type=Path, default=None, help="User-supplied POTCAR (skip auto-gen)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-handlers", action="store_true")
    p.add_argument("--max-errors", type=int, default=5)
    args = p.parse_args()

    if not args.poscar.exists():
        print(f"POSCAR not found: {args.poscar}", file=sys.stderr)
        return 1

    config = load_config(args.config)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    structure = Structure.from_file(str(args.poscar))

    user_incar, user_kpoints = resolve_input_files(
        args.work_dir, user_incar=args.incar, user_kpoints=args.kpoints, input_dir=args.input_dir,
    )
    build_optics_inputs(
        structure, args.work_dir, user_incar=user_incar, user_kpoints=user_kpoints, cshift=args.cshift,
    )

    if user_incar is None:
        from pymatgen.io.vasp.inputs import Incar
        inc = Incar.from_file(str(args.work_dir / "INCAR"))
        if "NBANDS" in inc:
            inc["NBANDS"] = int(inc["NBANDS"] * args.nbands_factor)
            inc.write_file(str(args.work_dir / "INCAR"))

    if args.potcar is not None:
        import shutil
        shutil.copy2(args.potcar, args.work_dir / "POTCAR")
    else:
        try:
            generate_potcar(args.work_dir / "POSCAR", args.work_dir,
                            functional=config.potcar.get("functional", "PBE"),
                            backend=config.potcar.get("backend", "vasp-potcar"))
        except Exception as e:
            print(f"WARN: POTCAR gen failed: {e}", file=sys.stderr)

    if args.dry_run:
        print(f"DRY RUN: optics inputs in {args.work_dir}")
        return 0

    cmd = resolve_vasp_command(config, args.executor)
    submit_script = build_submit_script(config, executor_override=args.executor, job_name="vasp-optics")
    submit_and_emit_async(
        args.work_dir,
        cmd,
        config,
        executor_override=args.executor,
        submit_script=submit_script,
        job_name="vasp-optics",
        task_kind="vasp_optics",
        display_name=args.poscar.stem or "vasp-optics",
        config_path=args.config,
    )
    summary = {
        "submitted": True,
        "work_dir": str(args.work_dir.resolve()),
        "task_kind": "vasp_optics",
        "note": "LOPTICS results in vasprun.xml after gateway poll.",
    }
    (args.work_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
