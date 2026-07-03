"""HSE06 hybrid functional static SCF (use alongside KPOINTS_OPT for band-path)."""
from __future__ import annotations

from .base import base_incar


def build(structure, traits) -> dict:
    incar = base_incar(structure, traits)
    incar.update({
        "LHFCALC": True,
        "HFSCREEN": 0.2,
        "AEXX": 0.25,
        "ALGO": "Damped",
        "TIME": 0.4,
        "PRECFOCK": "Fast",
        "LASPH": True,
        "NELMIN": 5,
        "EDIFF": 1e-5,
        "ISMEAR": 0,
        "SIGMA": 0.05,
        "LWAVE": True,
        "LCHARG": False,
        "PREC": "Accurate",
    })
    return incar
