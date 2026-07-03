#!/usr/bin/env python3
"""vasp-magnetic CLI — FM / AFM / non-collinear / SOC single-point or relax."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pymatgen.core import Structure

from vasp_skills_lib import load_config
from vasp_skills_lib.inputs.sets import build_magnetic_inputs, resolve_input_files
from vasp_skills_lib.potcar import generate_potcar
from vasp_skills_lib.runner import build_submit_script, resolve_vasp_command, submit_and_emit_async


def _parse_magmom(spec: str, structure: Structure) -> list:
    if not spec:
        return []
    if any(c in spec for c in (":", ",")) and any(s in spec.lower() for s in ("up", "down")):
        items = [x.strip() for x in spec.split(",")]
        result = []
        for item in items:
            _, val = item.split(":")
            v = val.strip().lower()
            if v == "up":
                result.append(4.0)
            elif v == "down":
                result.append(-4.0)
            else:
                result.append(float(v))
        return result
    return [float(x) for x in spec.split()]


def main() -> int:
    p = argparse.ArgumentParser(prog="vasp-magnetic")
    p.add_argument("poscar", type=Path)
    p.add_argument("--work-dir", type=Path, default=Path("./mag"))
    p.add_argument("--config-type", choices=["fm", "afm", "fim", "nm"], default="fm")
    p.add_argument("--magmom", default="", help="MAGMOM spec, e.g. 'Fe:up,Fe:down,O:0,O:0'")
    p.add_argument("--noncollinear", action="store_true", help="LNONCOLLINEAR=.TRUE.")
    p.add_argument("--soc", action="store_true", help="LSORBIT=.TRUE. (implies noncollinear)")
    p.add_argument("--quantization-axis", nargs=3, type=float, default=None, help="SAXIS vector for SOC")
    p.add_argument("--task", choices=["relax", "scf"], default="scf")
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

    overrides = {"ISPIN": 2 if args.config_type != "nm" else 1}
    magmom = _parse_magmom(args.magmom, structure)
    if magmom:
        overrides["MAGMOM"] = magmom
    if args.noncollinear or args.soc:
        overrides["LNONCOLLINEAR"] = True
    if args.soc:
        overrides["LSORBIT"] = True
        overrides["ICHARG"] = 11
        if args.quantization_axis:
            overrides["SAXIS"] = list(args.quantization_axis)

    user_incar, user_kpoints = resolve_input_files(
        args.work_dir, user_incar=args.incar, user_kpoints=args.kpoints, input_dir=args.input_dir,
    )
    build_magnetic_inputs(
        structure, args.work_dir, task=args.task,
        user_incar=user_incar, user_kpoints=user_kpoints,
        incar_overrides=overrides,
    )

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
        print(f"DRY RUN: magnetic inputs in {args.work_dir}")
        return 0

    cmd = resolve_vasp_command(config, args.executor)
    if (args.noncollinear or args.soc) and "vasp_std" in cmd and "vasp_ncl" not in cmd:
        print(f"WARN: non-collinear/SOC usually requires vasp_ncl. Current cmd: {cmd}", file=sys.stderr)
    submit_script = build_submit_script(config, executor_override=args.executor, job_name="vasp-magnetic")
    submit_and_emit_async(
        args.work_dir,
        cmd,
        config,
        executor_override=args.executor,
        submit_script=submit_script,
        job_name="vasp-magnetic",
        task_kind="vasp_magnetic",
        display_name=args.poscar.stem or "vasp-magnetic",
        config_path=args.config,
    )
    summary = {
        "submitted": True,
        "work_dir": str(args.work_dir.resolve()),
        "task_kind": "vasp_magnetic",
        "note": "magnetic moments in OSZICAR/OUTCAR after gateway poll.",
    }
    (args.work_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
