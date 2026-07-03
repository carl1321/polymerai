#!/usr/bin/env python3
"""vasp-dos CLI — uniform-mesh NSCF for (projected) DOS."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from pymatgen.core import Structure

from vasp_skills_lib import load_config
from vasp_skills_lib.inputs.sets import build_dos_inputs
from vasp_skills_lib.potcar import generate_potcar
from vasp_skills_lib.runner import build_submit_script, resolve_vasp_command, submit_and_emit_async


def main() -> int:
    p = argparse.ArgumentParser(prog="vasp-dos")
    p.add_argument("poscar", type=Path)
    p.add_argument("--scf-dir", type=Path, required=True, help="directory with CHGCAR from vasp-scf")
    p.add_argument("--work-dir", type=Path, default=Path("./dos"))
    p.add_argument("--nedos", type=int, default=3000)
    p.add_argument("--kpt-scale", type=float, default=2.0, help="density multiplier vs SCF KPOINTS")
    p.add_argument("--incar", type=Path, default=None)
    p.add_argument("--input-dir", type=Path, default=None, help="Directory with pre-built INCAR (KPOINTS ignored for dos)")
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
        print(f"CHGCAR not found in --scf-dir={args.scf_dir}. Run vasp-scf first.", file=sys.stderr)
        return 1

    config = load_config(args.config)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    structure = Structure.from_file(str(args.poscar))

    user_incar = args.incar
    if args.input_dir:
        candidate = args.input_dir / "INCAR"
        if candidate.exists():
            user_incar = candidate

    build_dos_inputs(structure, args.work_dir, user_incar=user_incar, nedos=args.nedos,
                     incar_overrides={"ICHARG": 11, "LORBIT": 11, "ISMEAR": -5})

    scf_kp = args.scf_dir / "KPOINTS"
    if scf_kp.exists() and args.kpt_scale != 1.0:
        lines = scf_kp.read_text(encoding="utf-8").splitlines()
        if len(lines) >= 4:
            try:
                parts = [max(1, int(round(int(x) * args.kpt_scale))) for x in lines[3].split()[:3]]
                lines[3] = " ".join(str(x) for x in parts)
                (args.work_dir / "KPOINTS").write_text("\n".join(lines) + "\n", encoding="utf-8")
            except ValueError:
                pass

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
    submit_script = build_submit_script(config, executor_override=args.executor, job_name="vasp-dos")
    submit_and_emit_async(
        args.work_dir,
        cmd,
        config,
        executor_override=args.executor,
        submit_script=submit_script,
        job_name="vasp-dos",
        task_kind="vasp_dos",
        display_name=args.poscar.stem or "vasp-dos",
        config_path=args.config,
    )
    summary = {
        "submitted": True,
        "work_dir": str(args.work_dir.resolve()),
        "task_kind": "vasp_dos",
        "note": "dos summary after gateway poll and fetch.",
    }
    (args.work_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
