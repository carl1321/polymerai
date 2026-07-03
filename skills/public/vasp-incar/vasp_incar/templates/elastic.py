"""Elastic constants (IBRION=6, ISIF=3, NFREE=4 finite-difference strain)."""
from __future__ import annotations

from .base import base_incar


def build(structure, traits) -> dict:
    incar = base_incar(structure, traits)
    incar.update({
        "IBRION": 6,
        "ISIF": 3,
        "NSW": 1,
        "NFREE": 4,
        "POTIM": 0.015,
        "EDIFF": 1e-7,
        "PREC": "Accurate",
        "ISMEAR": 0,
        "SIGMA": 0.05,
        "LREAL": False,
        "LWAVE": False,
        "LCHARG": False,
    })
    return incar
