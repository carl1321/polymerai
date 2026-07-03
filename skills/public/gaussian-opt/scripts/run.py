"""gaussian-opt — CLI.

Thin wrapper: builds a Route/Link0 for geometry optimization and delegates
the retry/handler loop to `gaussian_skills_lib.run_with_retries`. The
template every other gaussian-* skill follows.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from gaussian_skills_lib import run_with_retries
from gaussian_skills_lib.inputs import (
    Link0,
    build_route,
    geometry_from_ase,
    scrf_keyword,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gaussian geometry optimization")
    ap.add_argument("structure", type=Path, help="Input structure (ASE-readable)")
    ap.add_argument("--preset", default="b3lyp-d3")
    ap.add_argument("--method", default=None)
    ap.add_argument("--basis", default=None)
    ap.add_argument("--charge", type=int, default=0)
    ap.add_argument("--mult", type=int, default=1)
    ap.add_argument("--solvent", default=None)
    ap.add_argument("--tight", action="store_true")
    ap.add_argument("--mem", default="16GB")
    ap.add_argument("--nproc", type=int, default=8)
    ap.add_argument("--work-dir", type=Path, default=Path("./opt_run"))
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    from ase.io import read
    atoms = read(str(args.structure))

    extra = []
    if args.tight:
        extra.extend(["Opt=Tight", "SCF=Tight"])
    if args.solvent:
        extra.append(scrf_keyword(model="SMD", solvent=args.solvent))

    route = build_route(
        "opt", preset=args.preset, method=args.method, basis=args.basis,
        extra_keywords=extra,
    )
    link0 = Link0(chk="opt.chk", mem=args.mem, nprocshared=args.nproc)

    code, _ = run_with_retries(
        route=route, link0=link0,
        title=f"gaussian-opt: {args.structure.name}",
        charge=args.charge, mult=args.mult,
        geometry=geometry_from_ase(atoms),
        work_dir=args.work_dir,
        max_retries=args.max_retries,
        dry_run=args.dry_run,
    )
    return code


if __name__ == "__main__":
    sys.exit(main())
