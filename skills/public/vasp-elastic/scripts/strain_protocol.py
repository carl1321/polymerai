"""Elastic strain protocol — 6 independent strain directions, 2 magnitudes each.

The 6 Voigt strain components are: ε1=xx, ε2=yy, ε3=zz, ε4=yz, ε5=xz, ε6=xy.
For each, we apply ±δ (typical δ=0.5%) to the relaxed lattice and re-relax ions
(ISIF=2). Stresses from all 12 calculations are fitted linearly to extract C_ij.

This is a physics convention — do NOT use modeling's generic strain/supercell.
"""

from __future__ import annotations

import numpy as np
from pymatgen.core import Structure


VOIGT_TO_MATRIX = {
    1: (0, 0),
    2: (1, 1),
    3: (2, 2),
    4: (1, 2),  # and (2,1) symmetrically
    5: (0, 2),
    6: (0, 1),
}


def strain_matrix(voigt_index: int, magnitude: float) -> np.ndarray:
    """Return deformation gradient F = I + ε (engineering strain, small-strain approx).

    Voigt 1-3 are normal strains, 4-6 are shear strains (factor 2 off-diagonal as
    per engineering convention).
    """
    eps = np.zeros((3, 3))
    i, j = VOIGT_TO_MATRIX[voigt_index]
    if i == j:
        eps[i, j] = magnitude
    else:
        # engineering shear: ε_ij = magnitude / 2 placed symmetrically
        eps[i, j] = magnitude / 2.0
        eps[j, i] = magnitude / 2.0
    return np.eye(3) + eps


def generate_strained_structures(
    relaxed: Structure,
    magnitude: float = 0.005,
) -> list[tuple[str, Structure]]:
    """Return 12 (tag, structure) pairs: s01..s12 covering ±δ across 6 strains."""
    results: list[tuple[str, Structure]] = []
    idx = 0
    for voigt in range(1, 7):
        for sign in (+1, -1):
            idx += 1
            F = strain_matrix(voigt, sign * magnitude)
            new_lat = np.dot(F, relaxed.lattice.matrix.T).T
            strained = Structure(
                lattice=new_lat,
                species=[s.specie for s in relaxed.sites],
                coords=relaxed.frac_coords,  # ions move with cell; positions re-relax later
                coords_are_cartesian=False,
            )
            tag = f"s{idx:02d}_v{voigt}_{'p' if sign > 0 else 'm'}"
            results.append((tag, strained))
    return results
