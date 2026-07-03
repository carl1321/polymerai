"""CLI entry point for vasp-incar."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _cmd_generate(args: argparse.Namespace) -> int:
    from .generator import generate

    overrides: dict = {}
    if args.set:
        for kv in args.set:
            if "=" not in kv:
                print(f"ignoring malformed --set '{kv}'", file=sys.stderr)
                continue
            k, v = kv.split("=", 1)
            try:
                overrides[k.strip().upper()] = float(v) if v.replace(".", "", 1).replace("-", "", 1).isdigit() else v
            except ValueError:
                overrides[k.strip().upper()] = v

    result = generate(
        args.calc_type,
        args.poscar,
        out_dir=args.out,
        user_overrides=overrides,
        encut=args.encut,
        kpt_density=args.kpt_density,
    )
    print(f"Wrote {result.incar_path}")
    print(f"Wrote {result.kpoints_path}")
    if result.kpoints_opt_path:
        print(f"Wrote {result.kpoints_opt_path}")
    print(f"System: {result.traits}")
    errors = [v for v in result.violations if v.severity == "error"]
    warnings = [v for v in result.violations if v.severity != "error"]
    for v in result.violations:
        print(v)
    return 1 if errors else 0


def _cmd_validate(args: argparse.Namespace) -> int:
    from .validator import parse_incar, validate

    incar = parse_incar(args.incar)
    context: dict = {}
    if args.poscar:
        from . import system_detector as sd

        t = sd.detect(args.poscar)
        context = {"n_atoms": t.n_atoms, "is_metal": t.is_metal_guess,
                   "lattice_type": t.lattice_type}
    violations = validate(incar, context=context)
    for v in violations:
        print(v)
    errors = [v for v in violations if v.severity == "error"]
    if not violations:
        print("OK: no rule violations")
    return 1 if errors else 0


def _cmd_explain(args: argparse.Namespace) -> int:
    from .explainer import explain

    print(explain(args.tag))
    return 0


def _cmd_recommend(args: argparse.Namespace) -> int:
    from . import system_detector as sd
    from .generator import _load_template

    traits = sd.detect(args.poscar)
    build = _load_template(args.calc_type)
    from pymatgen.core import Structure

    s = Structure.from_file(args.poscar)
    incar = build(s, traits)
    print(f"System detected: {traits}")
    print("Proposed INCAR (template-only, no rule overrides, no file written):")
    print(json.dumps({k: _jsonable(v) for k, v in incar.items()}, indent=2))
    return 0


def _jsonable(v):
    try:
        json.dumps(v)
        return v
    except TypeError:
        return str(v)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="vasp-incar",
        description="VASP INCAR/KPOINTS generation, validation, and explanation.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="Write INCAR + KPOINTS for a calc type")
    g.add_argument("calc_type",
                   choices=("relax", "static", "band", "dos",
                            "phonon-finite", "phonon-dfpt", "elastic", "hse",
                            "scan", "optical", "defect"))
    g.add_argument("--poscar", required=True)
    g.add_argument("--out", default="./inputs")
    g.add_argument("--encut", type=float, default=None)
    g.add_argument("--kpt-density", type=int, default=1000,
                   help="Reciprocal k-point density (kppa); ignored for band mode")
    g.add_argument("--set", action="append", default=[],
                   help="Additional INCAR overrides, e.g. --set ENCUT=520 --set LDAU=.TRUE.")
    g.set_defaults(func=_cmd_generate)

    v = sub.add_parser("validate", help="Run the conflict detector on an existing INCAR")
    v.add_argument("--incar", required=True)
    v.add_argument("--poscar", default=None,
                   help="Optional POSCAR to enrich validator context")
    v.set_defaults(func=_cmd_validate)

    e = sub.add_parser("explain", help="Describe a single INCAR tag")
    e.add_argument("tag")
    e.set_defaults(func=_cmd_explain)

    r = sub.add_parser("recommend", help="Print parameter rationale, do not write files")
    r.add_argument("calc_type")
    r.add_argument("--poscar", required=True)
    r.set_defaults(func=_cmd_recommend)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
