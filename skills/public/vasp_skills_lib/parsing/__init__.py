"""Thin VASP result parsing shared across atomic skills."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CalcResult:
    converged: bool
    energy: float | None
    final_structure_path: Path | None
    band_gap: float | None = None
    errors: list[str] | None = None
    extra: dict[str, Any] | None = None



def _load_vasprun(work_dir: Path, *, parse_dos: bool = False, parse_eigen: bool = False):
    from pymatgen.io.vasp.outputs import Vasprun

    vr = work_dir / "vasprun.xml"
    if not vr.exists():
        return None, CalcResult(False, None, None, errors=["vasprun.xml not found"])
    try:
        return Vasprun(str(vr), parse_dos=parse_dos, parse_eigen=parse_eigen), None
    except Exception as e:
        return None, CalcResult(False, None, None, errors=[f"vasprun parse failed: {e}"])



def _base_extra(v) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    try:
        efermi = getattr(v, "efermi", None)
        if efermi is not None:
            extra["efermi"] = float(efermi)
    except Exception:
        pass
    try:
        actual = getattr(v, "actual_kpoints", None)
        if actual is not None:
            extra["num_kpoints"] = len(actual)
    except Exception:
        pass
    try:
        nbands = getattr(v, "parameters", {}).get("NBANDS")
        if nbands is not None:
            extra["nbands"] = int(nbands)
    except Exception:
        pass
    return extra



def parse_relax(work_dir: Path) -> CalcResult:
    v, err = _load_vasprun(work_dir, parse_dos=False, parse_eigen=False)
    if err is not None:
        return err
    contcar = work_dir / "CONTCAR"
    return CalcResult(
        converged=bool(v.converged),
        energy=float(v.final_energy) if v.final_energy is not None else None,
        final_structure_path=contcar if contcar.exists() else None,
        extra=_base_extra(v),
    )



def parse_scf(work_dir: Path) -> CalcResult:
    v, err = _load_vasprun(work_dir, parse_dos=False, parse_eigen=False)
    if err is not None:
        return err
    converged = bool(getattr(v, "converged_electronic", None) or getattr(v, "converged", False))
    energy = None
    try:
        energy = float(v.final_energy) if v.final_energy is not None else None
    except Exception:
        pass
    gap = None
    try:
        gap = v.get_band_structure().get_band_gap().get("energy")
    except Exception:
        pass
    return CalcResult(
        converged=converged,
        energy=energy,
        final_structure_path=None,
        band_gap=gap,
        extra=_base_extra(v),
    )



def parse_band(work_dir: Path) -> CalcResult:
    v, err = _load_vasprun(work_dir, parse_dos=False, parse_eigen=False)
    if err is not None:
        return err
    converged = bool(getattr(v, "converged_electronic", None) or getattr(v, "converged", False))
    energy = float(v.final_energy) if v.final_energy is not None else None
    extra = _base_extra(v)
    try:
        bs = v.get_band_structure(line_mode=True)
        gap = bs.get_band_gap().get("energy")
        extra["is_metal"] = bool(bs.is_metal())
        extra["is_spin_polarized"] = bool(getattr(bs, "is_spin_polarized", False))
        if hasattr(bs, "branches"):
            extra["num_branches"] = len(bs.branches)
        return CalcResult(
            converged=converged,
            energy=energy,
            final_structure_path=None,
            band_gap=gap,
            extra=extra,
        )
    except Exception as e:
        return CalcResult(
            converged=converged,
            energy=energy,
            final_structure_path=None,
            errors=[f"band parse failed: {e}"],
            extra=extra,
        )



def parse_dos(work_dir: Path) -> CalcResult:
    v, err = _load_vasprun(work_dir, parse_dos=True, parse_eigen=False)
    if err is not None:
        return err
    converged = bool(getattr(v, "converged_electronic", None) or getattr(v, "converged", False))
    energy = float(v.final_energy) if v.final_energy is not None else None
    extra = _base_extra(v)
    try:
        complete_dos = getattr(v, "complete_dos", None)
        extra["has_projected_dos"] = bool(complete_dos and getattr(complete_dos, "pdos", None))
    except Exception:
        pass
    return CalcResult(
        converged=converged,
        energy=energy,
        final_structure_path=None,
        extra=extra,
    )
