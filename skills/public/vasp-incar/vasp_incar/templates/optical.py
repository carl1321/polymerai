"""Optical properties (LOPTICS=True, high NBANDS, dense k-mesh)."""
from __future__ import annotations

from .base import base_incar


def build(structure, traits) -> dict:
    incar = base_incar(structure, traits)
    # Rough heuristic: double the electron count as NBANDS
    n_electrons = sum(getattr(sp, "Z", 0) for sp in structure.species)
    nbands = max(24, int(n_electrons))
    incar.update({
        "LOPTICS": True,
        "NEDOS": 2001,
        "CSHIFT": 0.1,
        "NBANDS": nbands,
        "EDIFF": 1e-7,
        "ISMEAR": 0,
        "SIGMA": 0.05,
        "LWAVE": False,
        "LCHARG": False,
        "PREC": "Accurate",
    })
    return incar
