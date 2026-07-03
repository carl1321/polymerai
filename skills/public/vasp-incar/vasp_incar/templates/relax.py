"""Structure relaxation (cell + ions)."""
from __future__ import annotations

from .base import base_incar


def build(structure, traits) -> dict:
    incar = base_incar(structure, traits)
    # Forces are not well defined with tetrahedron; force Gaussian during relax.
    if incar.get("ISMEAR") == -5:
        incar["ISMEAR"] = 0
        incar["SIGMA"] = 0.05
    incar.update({
        "IBRION": 2,
        "ISIF": 3,
        "NSW": 100,
        "EDIFF": 1e-6,
        "EDIFFG": -0.01,
        "PREC": "Accurate",
        "LWAVE": False,
        "LCHARG": False,
    })
    return incar
