#!/usr/bin/env python3
"""vasp-defect CLI — charge-state scan + formation-energy curve for a pre-built defect supercell.

The defect supercell MUST be built by the `modeling` skill first. This skill does NOT
generate vacancies/substitutions. Pipeline:

  1. For each charge state q, run a relax (NELECT shifted by -q)
  2. Read total energies; compose ΔN composition vector vs bulk
  3. Optionally apply image-charge correction (Makov-Payne first-order, or use
     pymatgen.analysis.defects for Freysoldt/Kumagai when LOCPOT files are present)
  4. Tabulate E_f(q, E_F) on a Fermi-level grid in [0, E_g]

Formation energy:
    E_f[D^q](E_F) = E[D^q] - E[bulk] - Σ Δn_i * μ_i + q*(E_F + E_VBM) + E_corr(q)
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

from pymatgen.core import Structure

from vasp_skills_lib import load_config
from vasp_skills_lib.inputs.sets import build_relax_inputs, build_scf_inputs
from vasp_skills_lib.potcar import generate_potcar
from vasp_skills_lib.runner import build_submit_script, emit_deerflow_async_envelope
from vasp_skills_lib.scheduler import JobScheduler
from vasp_skills_lib.executor import get_executor
from vasp_skills_lib.parsing import parse_relax, parse_scf

# Madelung constant for a point charge in a cubic supercell with neutralizing background.
# Used by the Makov-Payne first-order image-charge correction: E_corr = q^2 * αM / (2*ε*L)
_ALPHA_MADELUNG_CUBIC = 2.8373


def _prepare_one_charge(defect_structure: Structure, work_dir: Path, nelect_shift: int,
                        args, config, task: str = "relax") -> None:
    """Write VASP inputs for a single charge state. Does not run."""
    work_dir.mkdir(parents=True, exist_ok=True)
    overrides = {"NELECT": _base_nelect(defect_structure) + nelect_shift,
                 "ISIF": 2, "IBRION": 2, "LCHARG": True, "LWAVE": True}
    if args.correction in ("freysoldt", "kumagai"):
        overrides["LVHAR"] = True
    if task == "relax":
        build_relax_inputs(defect_structure, work_dir, user_incar=args.incar,
                          incar_overrides=overrides)
    else:
        overrides["EDIFF"] = 1e-6
        build_scf_inputs(defect_structure, work_dir, user_incar=args.incar,
                        incar_overrides=overrides)
    if args.potcar is not None:
        import shutil
        shutil.copy2(args.potcar, work_dir / "POTCAR")
    else:
        try:
            generate_potcar(work_dir / "POSCAR", work_dir,
                            functional=config.potcar.get("functional", "PBE"),
                            backend=config.potcar.get("backend", "vasp-potcar"))
        except Exception as e:
            print(f"WARN POTCAR {work_dir}: {e}", file=sys.stderr)


def _base_nelect(structure: Structure) -> float:
    """Count default valence electrons using pymatgen Potcar info."""
    from pymatgen.io.vasp.inputs import Potcar
    symbols: list[str] = []
    for site in structure.sites:
        s = site.specie.symbol
        if not symbols or symbols[-1] != s:
            symbols.append(s)
    total = 0.0
    try:
        pot = Potcar(symbols=symbols, functional="PBE")
        for element, single in zip(structure.composition.element_composition, pot):
            total += single.nelectrons * structure.composition[element]
    except Exception:
        pass
    return total


def _parse_mu(specs: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for spec in specs:
        k, v = spec.split("=")
        out[k.strip()] = float(v)
    return out


def _composition_delta(defect: Structure, bulk: Structure | None) -> dict[str, int]:
    """Δn_i = n_i^defect - n_i^bulk per element symbol."""
    if bulk is None:
        return {}
    delta: dict[str, int] = {}
    for el, n in defect.composition.element_composition.items():
        delta[el.symbol] = int(round(n - bulk.composition.element_composition[el]))
    for el, n in bulk.composition.element_composition.items():
        if el.symbol not in delta:
            delta[el.symbol] = int(round(-n))
    return {k: v for k, v in delta.items() if v != 0}


def _makov_payne(q: int, epsilon: float, supercell_volume_A3: float) -> float:
    """First-order Makov-Payne image-charge correction (eV) for a cubic supercell.

    E_corr = q^2 * αM / (2 * ε * L),  L = V^(1/3)
    Constants: αM = 2.8373 (cubic), 1/(4πε0) in eV·Å·e^-2 = 14.39964
    """
    if q == 0 or supercell_volume_A3 <= 0:
        return 0.0
    L = supercell_volume_A3 ** (1.0 / 3.0)
    return (q ** 2) * _ALPHA_MADELUNG_CUBIC * 14.39964 / (2.0 * epsilon * L)


def _parse_eps_tensor(spec: str | None, scalar: float | None) -> list[list[float]] | None:
    """Parse '--epsilon-tensor xx,yy,zz' or 'xx,xy,xz;yx,yy,yz;zx,zy,zz' into a 3x3 list.
    Falls back to isotropic from --epsilon when tensor not given."""
    if spec:
        rows = [r for r in spec.replace(" ", "").split(";") if r]
        if len(rows) == 1:
            vals = [float(x) for x in rows[0].split(",")]
            if len(vals) != 3:
                raise ValueError("--epsilon-tensor diagonal form needs 3 comma-separated values")
            return [[vals[0], 0, 0], [0, vals[1], 0], [0, 0, vals[2]]]
        if len(rows) == 3:
            mat = [[float(x) for x in r.split(",")] for r in rows]
            if any(len(row) != 3 for row in mat):
                raise ValueError("--epsilon-tensor full form needs 3x3 values")
            return mat
        raise ValueError("--epsilon-tensor must be 3 or 9 numbers")
    if scalar is not None:
        return [[scalar, 0, 0], [0, scalar, 0], [0, 0, scalar]]
    return None


def _freysoldt_correction(q: int, defect_dir: Path, bulk_dir: Path,
                          dielectric: float, defect_frac_coords: list[float] | None) -> float:
    """Compute Freysoldt correction (eV) from defect/bulk LOCPOT files.
    Returns 0.0 on failure (with stderr warning)."""
    if q == 0:
        return 0.0
    try:
        from pymatgen.analysis.defects.corrections.freysoldt import get_freysoldt_correction
        from pymatgen.io.vasp.outputs import Locpot
        d_loc = Locpot.from_file(str(defect_dir / "LOCPOT"))
        b_loc = Locpot.from_file(str(bulk_dir / "LOCPOT"))
        result = get_freysoldt_correction(
            q=q, dielectric=float(dielectric),
            defect_locpot=d_loc, bulk_locpot=b_loc,
            defect_frac_coords=defect_frac_coords,
        )
        return float(result.correction_energy)
    except Exception as e:
        print(f"WARN Freysoldt q={q:+d}: {e}", file=sys.stderr)
        return 0.0


def _kumagai_correction(q: int, defect_struct: Structure, bulk_struct: Structure,
                        eps_tensor: list[list[float]]) -> float:
    """Compute Kumagai/EFNV anisotropic correction (eV). Returns 0.0 on failure."""
    if q == 0:
        return 0.0
    try:
        from pymatgen.analysis.defects.corrections.kumagai import get_efnv_correction
        result = get_efnv_correction(
            charge=q, defect_structure=defect_struct,
            bulk_structure=bulk_struct, dielectric_tensor=eps_tensor,
        )
        return float(result.correction_energy)
    except Exception as e:
        print(f"WARN Kumagai q={q:+d}: {e}", file=sys.stderr)
        return 0.0


def _read_vbm(bulk_dir: Path) -> float | None:
    """Try to read VBM (eV, absolute) from bulk vasprun.xml."""
    from pymatgen.io.vasp.outputs import Vasprun
    try:
        v = Vasprun(str(bulk_dir / "vasprun.xml"), parse_eigen=True, parse_dos=False)
        bs = v.get_band_structure()
        vbm = bs.get_vbm()
        return float(vbm["energy"]) if vbm and vbm.get("energy") is not None else None
    except Exception:
        return None


def _read_band_gap(bulk_dir: Path) -> float | None:
    from pymatgen.io.vasp.outputs import Vasprun
    try:
        v = Vasprun(str(bulk_dir / "vasprun.xml"), parse_eigen=True, parse_dos=False)
        return float(v.get_band_structure().get_band_gap().get("energy") or 0.0)
    except Exception:
        return None


def _formation_curve(results: list[dict], bulk_energy: float, delta_n: dict[str, int],
                     mus: dict[str, float], vbm: float, gap: float,
                     epsilon: float | None, eps_tensor: list[list[float]] | None,
                     supercell_volume: float | None,
                     correction: str, e_corr_user: dict[int, float],
                     defect_frac_coords: list[float] | None,
                     bulk_dir: Path | None, bulk_struct: Structure | None,
                     defect_struct: Structure | None,
                     n_grid: int = 51) -> dict:
    """Compute E_f(q, E_F) on a uniform Fermi-level grid in [0, gap]."""
    e_fermi = [gap * i / (n_grid - 1) for i in range(n_grid)] if gap > 0 else [0.0]
    mu_term = sum(delta_n.get(k, 0) * mus.get(k, 0.0) for k in delta_n)

    by_charge = []
    for r in results:
        if r.get("energy_eV") is None or not r.get("success"):
            by_charge.append({"charge": r["charge"], "skipped": True})
            continue
        q = r["charge"]
        if q in e_corr_user:
            e_corr = e_corr_user[q]
        elif correction == "makov-payne" and epsilon and supercell_volume:
            e_corr = _makov_payne(q, epsilon, supercell_volume)
        elif correction == "freysoldt" and epsilon and bulk_dir is not None:
            e_corr = _freysoldt_correction(
                q, Path(r["work_dir"]), bulk_dir, epsilon, defect_frac_coords)
        elif correction == "kumagai" and eps_tensor and bulk_struct is not None and defect_struct is not None:
            e_corr = _kumagai_correction(q, defect_struct, bulk_struct, eps_tensor)
        else:
            e_corr = 0.0
        ef_curve = [
            r["energy_eV"] - bulk_energy - mu_term + q * (ef + vbm) + e_corr
            for ef in e_fermi
        ]
        by_charge.append({
            "charge": q,
            "energy_eV": r["energy_eV"],
            "e_corr_eV": e_corr,
            "E_f_at_VBM": ef_curve[0],
            "E_f_at_CBM": ef_curve[-1],
            "E_f_curve": ef_curve,
        })

    return {
        "fermi_grid_eV": e_fermi,
        "mu_term_eV": mu_term,
        "VBM_eV": vbm,
        "band_gap_eV": gap,
        "delta_composition": delta_n,
        "by_charge": by_charge,
    }


def defect_detached_finalize(work_dir: Path, meta: dict) -> dict:
    """Build full defect summary after all charge jobs finished (for gateway poll)."""
    defect_poscar = Path(meta["defect_poscar"])
    bulk_dir = Path(meta["bulk_dir"])
    defect = Structure.from_file(str(defect_poscar))
    mus = _parse_mu(list(meta.get("mu") or []))
    e_corr_user = {
        int(s.split("=")[0]): float(s.split("=")[1])
        for s in list(meta.get("e_corr") or [])
        if "=" in str(s)
    }
    eps_tensor = _parse_eps_tensor(meta.get("epsilon_tensor"), meta.get("epsilon"))

    results: list[dict] = []
    for q in meta["charges"]:
        sub = work_dir / f"q_{q:+d}"
        try:
            parsed = parse_relax(sub)
            results.append({
                "charge": q,
                "charge_shift": -q,
                "converged": parsed.converged,
                "energy_eV": parsed.energy,
                "success": parsed.converged and parsed.energy is not None,
                "work_dir": str(sub),
            })
        except Exception as e:
            results.append({
                "charge": q,
                "charge_shift": -q,
                "converged": False,
                "energy_eV": None,
                "success": False,
                "work_dir": str(sub),
                "error": str(e),
            })

    bulk = parse_relax(bulk_dir)
    bulk_energy = bulk.energy
    vbm = _read_vbm(bulk_dir) or 0.0
    gap = _read_band_gap(bulk_dir) or 0.0

    from pymatgen.io.vasp.outputs import Vasprun
    try:
        bulk_struct = Vasprun(str(bulk_dir / "vasprun.xml")).final_structure
        vol = float(bulk_struct.volume)
    except Exception:
        bulk_struct, vol = None, None
    delta_n = _composition_delta(defect, bulk_struct)

    dfc = meta.get("defect_frac_coords")
    if dfc is not None:
        dfc = list(dfc)

    curve = None
    if bulk_energy is not None:
        curve = _formation_curve(
            results,
            bulk_energy,
            delta_n,
            mus,
            vbm,
            gap,
            epsilon=meta.get("epsilon"),
            eps_tensor=eps_tensor,
            supercell_volume=vol,
            correction=str(meta.get("correction") or "none"),
            e_corr_user=e_corr_user,
            defect_frac_coords=dfc,
            bulk_dir=bulk_dir,
            bulk_struct=bulk_struct,
            defect_struct=defect,
            n_grid=int(meta.get("fermi_grid") or 51),
        )

    summary = {
        "defect_poscar": str(defect_poscar),
        "bulk_energy_eV": bulk_energy,
        "VBM_eV": vbm,
        "band_gap_eV": gap,
        "supercell_volume_A3": vol,
        "chemical_potentials": mus,
        "correction": meta.get("correction"),
        "delta_composition": delta_n,
        "by_charge_runs": results,
        "formation_energy": curve,
    }
    if meta.get("correction") == "freysoldt" and meta.get("epsilon") is None:
        summary["note"] = "Freysoldt requested but --epsilon missing; corrections defaulted to 0."
    elif meta.get("correction") == "kumagai" and eps_tensor is None:
        summary["note"] = "Kumagai requested but --epsilon-tensor/--epsilon missing; corrections defaulted to 0."
    return summary


def main() -> int:
    p = argparse.ArgumentParser(prog="vasp-defect")
    p.add_argument("defect_poscar", type=Path,
                   help="defect supercell POSCAR (build with modeling skill)")
    p.add_argument("--bulk-dir", type=Path, required=True,
                   help="directory with bulk supercell VASP run (vasprun.xml)")
    p.add_argument("--work-dir", type=Path, default=Path("./defect"))
    p.add_argument("--charges", nargs="+", type=int, default=[0],
                   help="list of charge states, e.g. -2 -1 0 1 2")
    p.add_argument("--mu", action="append", default=[],
                   help="chemical potential 'Ga=-3.0'; repeat for each element")
    p.add_argument("--correction", choices=["none", "makov-payne", "freysoldt", "kumagai"],
                   default="none",
                   help="makov-payne: inline cubic 1st-order. freysoldt: needs LOCPOT in each "
                        "charge dir + bulk-dir + --epsilon; auto-enables LVHAR=.TRUE. "
                        "kumagai: anisotropic EFNV, needs --epsilon-tensor.")
    p.add_argument("--epsilon", type=float, default=None,
                   help="static dielectric constant (scalar) for Makov-Payne or Freysoldt")
    p.add_argument("--epsilon-tensor", default=None,
                   help="3x3 dielectric tensor for Kumagai. Diagonal: 'εxx,εyy,εzz'. "
                        "Full: 'xx,xy,xz;yx,yy,yz;zx,zy,zz'. Use vasp-dielectric to obtain.")
    p.add_argument("--defect-frac-coords", nargs=3, type=float, default=None, metavar=("X", "Y", "Z"),
                   help="defect fractional coords for Freysoldt potential alignment "
                        "(auto-inferred from composition delta if omitted)")
    p.add_argument("--e-corr", action="append", default=[],
                   help="precomputed correction per charge, e.g. '+1=0.18'; overrides --correction")
    p.add_argument("--fermi-grid", type=int, default=51)
    p.add_argument("--incar", type=Path, default=None)
    p.add_argument("--executor", choices=["local", "ssh", "scnet"], default=None)
    p.add_argument("--config", type=Path, default=None)
    p.add_argument("--potcar", type=Path, default=None, help="User-supplied POTCAR (skip auto-gen)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-handlers", action="store_true")
    p.add_argument("--max-errors", type=int, default=5)
    p.add_argument("--max-concurrent", type=int, default=8,
                   help="并发提交的最大 charge 态数 (默认 8)")
    p.add_argument("--poll-interval", type=int, default=60)
    p.add_argument("--no-resume", dest="resume", action="store_false")
    p.set_defaults(resume=True)
    args = p.parse_args()

    if not args.defect_poscar.exists():
        print(f"defect POSCAR not found: {args.defect_poscar}", file=sys.stderr)
        return 1
    if not (args.bulk_dir / "vasprun.xml").exists():
        print(f"bulk vasprun.xml not found in {args.bulk_dir}", file=sys.stderr)
        return 1

    config = load_config(args.config)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    defect = Structure.from_file(str(args.defect_poscar))
    submit_script = build_submit_script(config, executor_override=args.executor, job_name="vasp-defect")
    state_file = args.work_dir / ".calc_runtime" / "defect_jobs.json"
    build_map: dict[str, object] = {}

    for q in args.charges:
        sub = args.work_dir / f"q_{q:+d}"
        if args.dry_run:
            print(f"DRY RUN: would compute q={q:+d} in {sub}")
            continue
        _prepare_one_charge(defect, sub, nelect_shift=-q, args=args, config=config, task="relax")
        build_map[str(sub.resolve())] = (lambda s=submit_script: s)

    if args.dry_run:
        return 0

    entries = [
        {"work_dir": str((args.work_dir / f"q_{q:+d}").resolve()), "job_name": f"vasp-defect-q{q:+d}"}
        for q in args.charges
    ]
    meta = {
        "kind": "defect",
        "bulk_dir": str(args.bulk_dir.resolve()),
        "defect_poscar": str(args.defect_poscar.resolve()),
        "charges": list(args.charges),
        "mu": list(args.mu),
        "correction": args.correction,
        "epsilon": args.epsilon,
        "epsilon_tensor": args.epsilon_tensor,
        "e_corr": list(args.e_corr),
        "fermi_grid": args.fermi_grid,
        "defect_frac_coords": list(args.defect_frac_coords) if args.defect_frac_coords else None,
        "submit_script": submit_script,
        "entries": entries,
        "max_concurrent": args.max_concurrent,
        "poll_interval": args.poll_interval,
        "max_errors": args.max_errors,
        "use_handlers": not args.no_handlers,
        "executor": args.executor,
    }
    rt = args.work_dir / ".calc_runtime"
    rt.mkdir(parents=True, exist_ok=True)
    (rt / "detached_group.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    with get_executor(config, args.executor) as ex:
        sched = JobScheduler(
            ex,
            state_file=state_file,
            max_concurrent=args.max_concurrent,
            poll_interval=args.poll_interval,
            max_errors=args.max_errors,
            use_handlers=not args.no_handlers,
        )
        for q in args.charges:
            sub = args.work_dir / f"q_{q:+d}"
            sched.add(
                sub,
                build_script=build_map[str(sub.resolve())],
                job_name=f"vasp-defect-q{q:+d}",
            )
        if args.resume:
            sched.restore(build_scripts=build_map, on_dones=None)
        sched.submit_all()

    poll_cmd = " ".join(
        [
            "python",
            "-m",
            "vasp_skills_lib.scheduler_group_poll",
            "--work-root",
            shlex.quote(str(args.work_dir.resolve())),
            "--state-file",
            shlex.quote(str(state_file.resolve())),
        ]
        + (["--config", shlex.quote(str(args.config.resolve()))] if args.config is not None else [])
    )
    emit_deerflow_async_envelope(
        work_dir=args.work_dir,
        config_path=args.config,
        job_id=None,
        task_kind="vasp_defect",
        display_name=args.defect_poscar.stem or "vasp-defect",
        poll_interval_seconds=max(args.poll_interval, 60),
        poll_command=poll_cmd,
    )
    stub = {
        "submitted": True,
        "task_kind": "vasp_defect",
        "charges": list(args.charges),
        "work_dir": str(args.work_dir.resolve()),
        "note": "formation_energy summary.json after gateway polls complete all charge jobs.",
    }
    (args.work_dir / "summary.json").write_text(
        json.dumps(stub, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(stub, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
