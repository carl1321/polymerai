"""Point-defect calc: fixed cell (ISIF=2), Γ-only k-mesh, large ENCUT."""
from __future__ import annotations

from .base import base_incar


def build(structure, traits) -> dict:
    incar = base_incar(structure, traits)
    current_encut = incar.get("ENCUT", 520)
    # Defect supercells are normally large; use real-space projectors only then.
    lreal = "Auto" if traits.n_atoms >= 20 else False
    incar.update({
        "IBRION": 2,
        "ISIF": 2,
        "NSW": 150,
        "ENCUT": max(float(current_encut), 520.0),
        "EDIFF": 1e-6,
        "EDIFFG": -0.02,
        "ISMEAR": 0,
        "SIGMA": 0.05,
        "LREAL": lreal,
        "LCHARG": True,
        "LWAVE": False,
        "PREC": "Accurate",
    })
    return incar
