"""Detect structural traits that drive INCAR / KPOINTS choices.

Returns metal / semiconductor / insulator guess (based on composition
heuristics when no bandgap is known), the Bravais lattice family (for
Γ-centered vs Monkhorst-Pack decisions), and a list of 3d/4d/5d magnetic
elements present.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


MAGNETIC_3D = {"Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu"}
MAGNETIC_4F = {"Ce", "Pr", "Nd", "Pm", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er",
               "Tm", "Yb"}
# Elements typically producing metallic bulk compounds (very rough heuristic,
# only used when bandgap is unknown).
COMMON_METALS = {
    "Li", "Na", "K", "Rb", "Cs", "Mg", "Ca", "Sr", "Ba",
    "Al", "Ga", "In", "Sn", "Pb", "Bi",
    "Sc", "Y", "Ti", "Zr", "Hf", "V", "Nb", "Ta", "Cr", "Mo", "W",
    "Mn", "Tc", "Re", "Fe", "Ru", "Os", "Co", "Rh", "Ir",
    "Ni", "Pd", "Pt", "Cu", "Ag", "Au", "Zn", "Cd", "Hg",
}


@dataclass
class SystemTraits:
    bravais: str            # e.g. "cubic", "hexagonal", "tetragonal", ...
    space_group: str
    lattice_type: str       # "FCC" / "BCC" / "HEX" / "ORTHO" / "MONO" / "TRI"
    gamma_required: bool    # True if FCC / HEX / FCC-orthorhombic (VASP wiki §4.2)
    is_metal_guess: bool
    magnetic_elements: list[str] = field(default_factory=list)
    has_localized_f: bool = False
    n_atoms: int = 0


def _lattice_type(space_group_number: int) -> str:
    if 195 <= space_group_number <= 230:
        if space_group_number in (196, 202, 203, 209, 210, 216, 219, 225, 226, 227, 228):
            return "FCC"
        if space_group_number in (197, 199, 204, 211, 214, 217, 220, 229, 230):
            return "BCC"
        return "SC"
    if 143 <= space_group_number <= 194:
        return "HEX"
    if 75 <= space_group_number <= 142:
        return "TETRA"
    if 16 <= space_group_number <= 74:
        return "ORTHO"
    if 3 <= space_group_number <= 15:
        return "MONO"
    return "TRI"


def detect(poscar_path: str | Path) -> SystemTraits:
    from pymatgen.core import Structure
    from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

    s = Structure.from_file(str(poscar_path))
    sga = SpacegroupAnalyzer(s, symprec=0.1)
    sgn = sga.get_space_group_number()
    sg_symbol = sga.get_space_group_symbol()
    crystal_system = sga.get_crystal_system()
    lat_type = _lattice_type(sgn)

    species = {sp.symbol for sp in s.species}
    magnetic = sorted(species & (MAGNETIC_3D | MAGNETIC_4F))
    has_f = bool(species & MAGNETIC_4F)

    # Metal guess: composition-only heuristic. If every species is a common
    # metal and no chalcogen / halogen / pnictogen is present, flag as metal.
    anions = {"O", "S", "Se", "Te", "F", "Cl", "Br", "I", "N", "P"}
    has_anion = bool(species & anions)
    all_metal = bool(species) and species.issubset(COMMON_METALS)
    metal_guess = all_metal and not has_anion

    return SystemTraits(
        bravais=crystal_system,
        space_group=f"{sg_symbol} ({sgn})",
        lattice_type=lat_type,
        gamma_required=lat_type in {"FCC", "HEX"},
        is_metal_guess=metal_guess,
        magnetic_elements=magnetic,
        has_localized_f=has_f,
        n_atoms=len(s),
    )


def auto_ismear(is_metal: bool | None, bandgap: float | None = None) -> tuple[int, float]:
    """Replicate atomate2's auto_ismear decision tree.

    Returns (ISMEAR, SIGMA).
    """
    if bandgap is None and is_metal is None:
        return 0, 0.2
    if bandgap is not None:
        if bandgap < 1e-4:
            return 2, 0.2
        return -5, 0.05
    return (2, 0.2) if is_metal else (-5, 0.05)
