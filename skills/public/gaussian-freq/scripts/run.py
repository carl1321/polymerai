"""gaussian-freq — vibrational + thermochemistry on a pre-optimized geometry.

Input may be `.xyz`, `.gjf`, or a Gaussian `.log` (in which case the last
optimized geometry is extracted via cclib).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from gaussian_skills_lib import run_with_retries
from gaussian_skills_lib.inputs import (
    Link0,
    Route,
    PRESETS,
    geometry_from_ase,
    scrf_keyword,
)


def _freq_keyword(*, anharmonic: bool, raman: bool, readfc: bool,
                  temperature: float | None, pressure: float | None) -> str:
    parts: list[str] = []
    if anharmonic:
        parts.append("Anharm")
    if raman:
        parts.append("Raman")
    if readfc:
        parts.append("ReadFC")
    if temperature is not None:
        parts.append(f"Temperature={temperature}")
    if pressure is not None:
        parts.append(f"Pressure={pressure}")
    if not parts:
        return "Freq"
    if len(parts) == 1:
        return f"Freq={parts[0]}"
    return f"Freq=({','.join(parts)})"


def _load_geometry(path: Path) -> str:
    """Read a structure as ASE Atoms, falling back to cclib for .log files."""
    if path.suffix.lower() == ".log":
        from gaussian_skills_lib.parsing import parse_log
        from ase import Atoms
        from ase.data import chemical_symbols
        parsed = parse_log(path)
        coords = parsed.get("geometries")
        atoms = parsed.get("atoms") or []
        if coords is None or len(atoms) == 0:
            raise SystemExit(f"Could not extract geometry from {path}")
        symbols = [chemical_symbols[int(z)] for z in atoms]
        a = Atoms(symbols=symbols, positions=list(coords[-1]))
        return geometry_from_ase(a)
    from ase.io import read
    return geometry_from_ase(read(str(path)))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gaussian frequency / thermochemistry")
    ap.add_argument("structure", type=Path,
                    help="Optimized structure (.xyz, .gjf, or Gaussian .log)")
    ap.add_argument("--preset", default="b3lyp-d3")
    ap.add_argument("--method", default=None)
    ap.add_argument("--basis", default=None)
    ap.add_argument("--charge", type=int, default=0)
    ap.add_argument("--mult", type=int, default=1)
    ap.add_argument("--solvent", default=None)
    ap.add_argument("--temperature", type=float, default=None,
                    help="Kelvin; default = Gaussian default (298.15)")
    ap.add_argument("--pressure", type=float, default=None, help="atm")
    ap.add_argument("--anharmonic", action="store_true")
    ap.add_argument("--raman", action="store_true")
    ap.add_argument("--readfc", action="store_true",
                    help="reuse force constants from --oldchk")
    ap.add_argument("--oldchk", default=None,
                    help="path to existing .chk for --readfc")
    ap.add_argument("--mem", default="16GB")
    ap.add_argument("--nproc", type=int, default=8)
    ap.add_argument("--work-dir", type=Path, default=Path("./freq_run"))
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.readfc and not args.oldchk:
        ap.error("--readfc requires --oldchk PATH")

    geometry = _load_geometry(args.structure)

    base = PRESETS.get(args.preset, PRESETS["b3lyp-d3"])
    method = args.method or base["method"]
    basis = args.basis if args.basis is not None else base["basis"]

    keywords: list[str] = list(base.get("extra", []))
    keywords.insert(0, _freq_keyword(
        anharmonic=args.anharmonic, raman=args.raman, readfc=args.readfc,
        temperature=args.temperature, pressure=args.pressure,
    ))
    if args.solvent:
        keywords.append(scrf_keyword(model="SMD", solvent=args.solvent))
    if args.readfc:
        keywords.append("Geom=AllCheck")

    route = Route(method=method, basis=basis, keywords=keywords)
    link0 = Link0(
        chk="freq.chk", oldchk=args.oldchk,
        mem=args.mem, nprocshared=args.nproc,
    )

    code, _ = run_with_retries(
        route=route, link0=link0,
        title=f"gaussian-freq: {args.structure.name}",
        charge=args.charge, mult=args.mult,
        geometry=geometry,
        work_dir=args.work_dir,
        max_retries=args.max_retries,
        dry_run=args.dry_run,
    )
    return code


if __name__ == "__main__":
    sys.exit(main())
