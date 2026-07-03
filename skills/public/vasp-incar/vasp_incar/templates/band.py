"""Non-self-consistent band structure (assumes prior static produced CHGCAR)."""
from __future__ import annotations

from .base import base_incar


def build(structure, traits) -> dict:
    incar = base_incar(structure, traits)
    incar.update({
        "IBRION": -1,
        "NSW": 0,
        "ISIF": 2,
        "ICHARG": 11,
        "ISMEAR": 0,
        "SIGMA": 0.05,
        "LORBIT": 11,
        "LCHARG": False,
        "LWAVE": False,
        "EDIFF": 1e-6,
        "PREC": "Accurate",
    })
    incar.pop("LREAL", None)
    return incar
