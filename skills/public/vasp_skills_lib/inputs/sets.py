"""Input set wrappers.

Philosophy:
  - Use pymatgen.io.vasp.sets as the base.
  - User-supplied INCAR/KPOINTS override defaults.
  - Shared builders only generate input files; they do not own workflow orchestration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pymatgen.core import Structure
from pymatgen.io.vasp.inputs import Incar, Kpoints, Poscar
from pymatgen.io.vasp.sets import MPNonSCFSet, MPRelaxSet, MPStaticSet


INPUT_METADATA_FILE = "metadata.json"



def _write_inputs(
    structure: Structure,
    work_dir: Path,
    incar: Incar,
    kpoints: Kpoints,
    user_incar: Path | None,
    user_kpoints: Path | None,
) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    Poscar(structure).write_file(str(work_dir / "POSCAR"))
    if user_incar:
        (work_dir / "INCAR").write_text(Path(user_incar).read_text(encoding="utf-8"), encoding="utf-8")
    else:
        incar.write_file(str(work_dir / "INCAR"))
    if user_kpoints:
        (work_dir / "KPOINTS").write_text(Path(user_kpoints).read_text(encoding="utf-8"), encoding="utf-8")
    else:
        kpoints.write_file(str(work_dir / "KPOINTS"))



def _write_metadata(
    work_dir: Path,
    *,
    calc_type: str,
    supported_skills: list[str],
    generated_by: str = "vasp_skills_lib.inputs.sets",
) -> None:
    import json

    (work_dir / INPUT_METADATA_FILE).write_text(
        json.dumps(
            {
                "calc_type": calc_type,
                "generated_by": generated_by,
                "supported_skills": supported_skills,
                "user_modified": False,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )



def resolve_input_files(
    work_dir: Path,
    *,
    user_incar: Path | None = None,
    user_kpoints: Path | None = None,
    input_dir: Path | None = None,
) -> tuple[Path | None, Path | None]:
    if input_dir is not None:
        incar = input_dir / "INCAR"
        kpoints = input_dir / "KPOINTS"
        return (incar if incar.exists() else None, kpoints if kpoints.exists() else None)
    if user_incar is not None or user_kpoints is not None:
        return user_incar, user_kpoints
    existing_incar = work_dir / "INCAR"
    existing_kpoints = work_dir / "KPOINTS"
    return (
        existing_incar if existing_incar.exists() else None,
        existing_kpoints if existing_kpoints.exists() else None,
    )



def build_relax_inputs(
    structure: Structure,
    work_dir: Path,
    user_incar: Path | None = None,
    user_kpoints: Path | None = None,
    incar_overrides: dict[str, Any] | None = None,
) -> Path:
    vis = MPRelaxSet(structure, user_incar_settings=incar_overrides or {})
    _write_inputs(structure, work_dir, vis.incar, vis.kpoints, user_incar, user_kpoints)
    _write_metadata(work_dir, calc_type="relax", supported_skills=["vasp-relax", "vasp-double-relax"])
    return work_dir



def build_scf_inputs(
    structure: Structure,
    work_dir: Path,
    user_incar: Path | None = None,
    user_kpoints: Path | None = None,
    incar_overrides: dict[str, Any] | None = None,
) -> Path:
    vis = MPStaticSet(structure, user_incar_settings=incar_overrides or {})
    _write_inputs(structure, work_dir, vis.incar, vis.kpoints, user_incar, user_kpoints)
    _write_metadata(work_dir, calc_type="scf", supported_skills=["vasp-scf"])
    return work_dir



def build_band_inputs(
    structure: Structure,
    work_dir: Path,
    user_incar: Path | None = None,
    user_kpoints: Path | None = None,
    line_density: int = 20,
    incar_overrides: dict[str, Any] | None = None,
) -> Path:
    vis = MPNonSCFSet(
        structure,
        mode="line",
        kpoints_line_density=line_density,
        user_incar_settings=incar_overrides or {},
    )
    _write_inputs(structure, work_dir, vis.incar, vis.kpoints, user_incar, user_kpoints)
    _write_metadata(work_dir, calc_type="band", supported_skills=["vasp-band"])
    return work_dir



def build_dos_inputs(
    structure: Structure,
    work_dir: Path,
    user_incar: Path | None = None,
    user_kpoints: Path | None = None,
    nedos: int = 3000,
    incar_overrides: dict[str, Any] | None = None,
) -> Path:
    overrides = {"NEDOS": nedos, "LORBIT": 11, **(incar_overrides or {})}
    vis = MPNonSCFSet(structure, mode="uniform", user_incar_settings=overrides)
    _write_inputs(structure, work_dir, vis.incar, vis.kpoints, user_incar, user_kpoints)
    _write_metadata(work_dir, calc_type="dos", supported_skills=["vasp-dos"])
    return work_dir



def build_dielectric_inputs(
    structure: Structure,
    work_dir: Path,
    user_incar: Path | None = None,
    user_kpoints: Path | None = None,
    incar_overrides: dict[str, Any] | None = None,
) -> Path:
    overrides = {
        "LEPSILON": True,
        "LPEAD": True,
        "IBRION": 8,
        "NSW": 1,
        "NCORE": 1,
        "EDIFF": 1e-8,
        "PREC": "Accurate",
        **(incar_overrides or {}),
    }
    return build_scf_inputs(structure, work_dir, user_incar, user_kpoints, overrides)



def build_magnetic_inputs(
    structure: Structure,
    work_dir: Path,
    *,
    task: str,
    user_incar: Path | None = None,
    user_kpoints: Path | None = None,
    incar_overrides: dict[str, Any] | None = None,
) -> Path:
    overrides = dict(incar_overrides or {})
    if task == "relax":
        return build_relax_inputs(structure, work_dir, user_incar, user_kpoints, overrides)
    overrides.setdefault("EDIFF", 1e-6)
    return build_scf_inputs(structure, work_dir, user_incar, user_kpoints, overrides)



def build_optics_inputs(
    structure: Structure,
    work_dir: Path,
    user_incar: Path | None = None,
    user_kpoints: Path | None = None,
    cshift: float = 0.1,
    incar_overrides: dict[str, Any] | None = None,
) -> Path:
    overrides = {
        "LOPTICS": True,
        "CSHIFT": cshift,
        "ALGO": "Normal",
        "NEDOS": 2000,
        "EDIFF": 1e-7,
        **(incar_overrides or {}),
    }
    return build_scf_inputs(structure, work_dir, user_incar, user_kpoints, overrides)



def build_lobster_inputs(
    structure: Structure,
    work_dir: Path,
    user_incar: Path | None = None,
    user_kpoints: Path | None = None,
    incar_overrides: dict[str, Any] | None = None,
) -> Path:
    overrides = {
        "ISYM": -1,
        "LWAVE": True,
        "LORBIT": 11,
        "NSW": 0,
        "IBRION": -1,
        "EDIFF": 1e-7,
        **(incar_overrides or {}),
    }
    return build_scf_inputs(structure, work_dir, user_incar, user_kpoints, overrides)
