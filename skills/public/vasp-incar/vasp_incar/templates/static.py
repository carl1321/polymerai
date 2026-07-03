"""Single-point static SCF (no ionic moves)."""
from __future__ import annotations

from .base import base_incar


def build(structure, traits) -> dict:
    incar = base_incar(structure, traits)
    incar.update({
        "IBRION": -1,
        "NSW": 0,
        "ISIF": 2,
        "EDIFF": 1e-6,
        "PREC": "Accurate",
        "LWAVE": True,
        "LCHARG": True,
        "LORBIT": 11,
    })
    return incar
