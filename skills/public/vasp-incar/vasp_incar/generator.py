"""Main pipeline: load POSCAR → detect → template → overrides → validate → write."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import kpoints as kpt_mod
from . import system_detector as sd
from . import validator as val_mod


@dataclass
class GenerationResult:
    incar_path: Path
    kpoints_path: Path
    kpoints_opt_path: Path | None
    violations: list[val_mod.Violation]
    traits: sd.SystemTraits
    incar_dict: dict


def _load_template(calc_type: str):
    """Dynamic dispatch onto vasp_incar.templates.<name>.build."""
    from importlib import import_module

    normalized = calc_type.replace("-", "_")
    try:
        mod = import_module(f"vasp_incar.templates.{normalized}")
    except ModuleNotFoundError as exc:
        raise ValueError(
            f"Unknown calc_type '{calc_type}'. "
            "Available: relax, static, band, dos, phonon-finite, phonon-dfpt, "
            "elastic, hse, scan, optical, defect."
        ) from exc
    return mod.build


def _merge_overrides(incar: dict, overrides: dict) -> dict:
    """Shallow merge; None values remove the key."""
    out = dict(incar)
    for k, v in overrides.items():
        if v is None:
            out.pop(k, None)
        else:
            out[k] = v
    return out


def _apply_rule_overrides(incar: dict, traits: sd.SystemTraits) -> dict:
    import yaml

    rules_path = Path(__file__).parent / "rules" / "overrides.yaml"
    if not rules_path.is_file():
        return incar
    rules = yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {}
    override = dict(incar)

    for rule in rules.get("rules", []):
        cond = rule.get("when", {})
        if "magnetic_elements_any" in cond:
            wanted = set(cond["magnetic_elements_any"])
            if not (set(traits.magnetic_elements) & wanted):
                continue
        if cond.get("has_localized_f") and not traits.has_localized_f:
            continue
        if "n_atoms_gt" in cond and not (traits.n_atoms > cond["n_atoms_gt"]):
            continue
        if "is_metal" in cond and traits.is_metal_guess != cond["is_metal"]:
            continue
        for k, v in rule.get("apply", {}).items():
            if v is None:
                override.pop(k, None)
            else:
                override[k] = v
    return override


def generate(
    calc_type: str,
    poscar_path: str | Path,
    *,
    out_dir: str | Path,
    user_overrides: dict | None = None,
    encut: float | None = None,
    kpt_density: int = 1000,
) -> GenerationResult:
    from pymatgen.core import Structure

    poscar_path = Path(poscar_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    structure = Structure.from_file(str(poscar_path))
    traits = sd.detect(poscar_path)

    build = _load_template(calc_type)
    incar = build(structure, traits)

    incar = _apply_rule_overrides(incar, traits)
    if encut is not None:
        incar["ENCUT"] = float(encut)
    if user_overrides:
        incar = _merge_overrides(incar, user_overrides)

    # KPOINTS
    kpoints_opt_path: Path | None = None
    if calc_type in ("band",):
        kp = kpt_mod.line_mode(structure, density=50)
    elif calc_type in ("hse",):
        mesh_kp = kpt_mod.mesh(structure, density=kpt_density,
                               gamma_required=traits.gamma_required)
        line_kp = kpt_mod.line_mode(structure, density=40)
        kp = mesh_kp
        kpoints_opt_path = kpt_mod.kpoints_opt_for_hse(mesh_kp, line_kp, out_dir)
    else:
        kp = kpt_mod.mesh(structure, density=kpt_density,
                          gamma_required=traits.gamma_required)
    kpoints_path = kpt_mod.write(kp, out_dir)

    # Write INCAR
    from pymatgen.io.vasp import Incar

    incar_obj = Incar(incar)
    incar_path = out_dir / "INCAR"
    incar_obj.write_file(str(incar_path))

    # Validate
    # For automatic meshes pymatgen sets num_kpts=0; estimate total grid points
    # as an upper bound on irreducible k-points for the tetrahedron check.
    n_kpts = kp.num_kpts or 0
    if not n_kpts and getattr(kp, "kpts", None):
        try:
            mesh = kp.kpts[0]
            n_kpts = int(mesh[0]) * int(mesh[1]) * int(mesh[2])
        except Exception:
            n_kpts = 0
    context = {
        "n_kpoints": n_kpts,
        "n_atoms": traits.n_atoms,
        "is_metal": traits.is_metal_guess,
        "lattice_type": traits.lattice_type,
    }
    violations = val_mod.validate(dict(incar_obj), context=context)

    return GenerationResult(
        incar_path=incar_path,
        kpoints_path=kpoints_path,
        kpoints_opt_path=kpoints_opt_path,
        violations=violations,
        traits=traits,
        incar_dict=dict(incar_obj),
    )
