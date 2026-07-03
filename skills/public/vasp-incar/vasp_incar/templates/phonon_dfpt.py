"""Phonon via DFPT (IBRION=8). Requires ADDGRID and tight EDIFF."""
from __future__ import annotations

from .base import base_incar


def build(structure, traits) -> dict:
    incar = base_incar(structure, traits)
    incar.update({
        "IBRION": 8,
        "NSW": 1,
        "EDIFF": 1e-8,
        "ISMEAR": 0,
        "SIGMA": 0.1,
        "IALGO": 38,
        "ADDGRID": True,
        "LREAL": False,
        "LWAVE": False,
        "LCHARG": False,
        "PREC": "Accurate",
    })
    return incar
