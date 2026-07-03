#!/usr/bin/env python3
"""vasp-band CLI — line-mode NSCF for band structure."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from pymatgen.core import Structure
from pymatgen.io.vasp.inputs import Kpoints
from pymatgen.symmetry.bandstructure import HighSymmKpath
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from vasp_skills_lib import load_config
from vasp_skills_lib.inputs.sets import build_band_inputs
from vasp_skills_lib.potcar import generate_potcar
from vasp_skills_lib.runner import build_submit_script, resolve_vasp_command, submit_and_emit_async


def main() -> int:
    p = argparse.ArgumentParser(prog="vasp-band")
    p.add_argument("poscar", type=Path)
    p.add_argument("--scf-dir", type=Path, required=True, help="directory with CHGCAR from vasp-scf")
    p.add_argument("--work-dir", type=Path, default=Path("./band"))
    p.add_argument("--line-density", type=int, default=20)
    p.add_argument("--incar", type=Path, default=None)
    p.add_argument("--input-dir", type=Path, default=None, help="Directory with pre-built INCAR (KPOINTS ignored for band)")
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
    chgcar = args.scf_dir / "CHGCAR"
    if not chgcar.exists():
        print(f"CHGCAR not found under --scf-dir={args.scf_dir}. Run vasp-scf first.", file=sys.stderr)
        return 1

    config = load_config(args.config)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    structure = Structure.from_file(str(args.poscar))
    prim = SpacegroupAnalyzer(structure).get_primitive_standard_structure()

    user_incar = args.incar
    if args.input_dir:
        candidate = args.input_dir / "INCAR"
        if candidate.exists():
            user_incar = candidate

    build_band_inputs(
        structure, args.work_dir, user_incar=user_incar,
        line_density=args.line_density,
        incar_overrides={"ICHARG": 11, "LORBIT": 11, "ISMEAR": 0, "SIGMA": 0.05},
    )
    kpath = HighSymmKpath(prim)
    kpts = Kpoints.automatic_linemode(args.line_density, kpath)
    kpts.write_file(str(args.work_dir / "KPOINTS"))

    shutil.copy2(chgcar, args.work_dir / "CHGCAR")
    if args.potcar is not None:
        shutil.copy2(args.potcar, args.work_dir / "POTCAR")
    else:
        try:
            generate_potcar(args.work_dir / "POSCAR", args.work_dir,
                            functional=config.potcar.get("functional", "PBE"),
                            backend=config.potcar.get("backend", "vasp-potcar"))
        except Exception as e:
            print(f"WARN: POTCAR gen failed: {e}", file=sys.stderr)

    if args.dry_run:
        print(f"DRY RUN: inputs in {args.work_dir}")
        return 0

    cmd = resolve_vasp_command(config, args.executor)
    submit_script = build_submit_script(config, executor_override=args.executor, job_name="vasp-band")
    submit_and_emit_async(
        args.work_dir,
        cmd,
        config,
        executor_override=args.executor,
        submit_script=submit_script,
        job_name="vasp-band",
        task_kind="vasp_band",
        display_name=args.poscar.stem or "vasp-band",
        config_path=args.config,
    )
    summary = {
        "submitted": True,
        "work_dir": str(args.work_dir.resolve()),
        "task_kind": "vasp_band",
        "note": "band summary after gateway poll and fetch.",
    }
    (args.work_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
