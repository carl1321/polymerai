"""High-resolution DOS calc (non-SCF; requires CHGCAR from a converged static)."""
from __future__ import annotations

from .base import base_incar


def build(structure, traits) -> dict:
    incar = base_incar(structure, traits)
    # Insulators: use tetrahedron if enough k-points; otherwise Gaussian
    if not traits.is_metal_guess:
        incar["ISMEAR"] = -5
    else:
        incar["ISMEAR"] = 0
        incar["SIGMA"] = 0.05
    incar.update({
        "IBRION": -1,
        "NSW": 0,
        "ISIF": 2,
        "ICHARG": 11,
        "NEDOS": 3001,
        "LORBIT": 11,
        "LCHARG": False,
        "LWAVE": False,
        "EDIFF": 1e-6,
        "PREC": "Accurate",
    })
    return incar
