"""Phonon via finite displacement (IBRION=-1 static runs on displaced supercells)."""
from __future__ import annotations

from .base import base_incar


def build(structure, traits) -> dict:
    incar = base_incar(structure, traits)
    incar.update({
        "IBRION": -1,
        "NSW": 0,
        "ISIF": 2,
        "EDIFF": 1e-8,
        "ISMEAR": 0,
        "SIGMA": 0.01,
        "IALGO": 38,
        "PREC": "Accurate",
        "LREAL": False,
        "LWAVE": False,
        "LCHARG": True,
        "ADDGRID": True,
    })
    return incar
