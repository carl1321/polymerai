"""Meta-GGA (R2SCAN by default). Requires LASPH=True and no GGA tag."""
from __future__ import annotations

from .base import base_incar


def build(structure, traits) -> dict:
    incar = base_incar(structure, traits)
    incar.pop("GGA", None)
    if incar.get("ISMEAR") == -5:
        incar["ISMEAR"] = 0
        incar["SIGMA"] = 0.05
    incar.update({
        "METAGGA": "R2SCAN",
        "LASPH": True,
        "LMIXTAU": True,
        "ALGO": "All",
        "EDIFF": 1e-6,
        "PREC": "Accurate",
        "LWAVE": True,
        "LCHARG": True,
    })
    return incar
