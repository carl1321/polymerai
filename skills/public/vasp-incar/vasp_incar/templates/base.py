"""Common INCAR defaults shared by every calculation type.

Bootstraps from pymatgen MPRelaxSet's YAML so we inherit MP-validated defaults
(EDIFF_PER_ATOM, ENCUT, LDAU U values, MAGMOM table). Each calc-type template
calls :func:`base_incar` then overrides what it needs.
"""
from __future__ import annotations

from typing import Any

from .. import system_detector as sd


def base_incar(structure, traits: sd.SystemTraits) -> dict[str, Any]:
    """Return the MP-style relaxation INCAR as a plain dict.

    We construct a pymatgen MPRelaxSet so we get the full default treatment
    (per-element MAGMOM, U values, ENCUT from POTCAR, etc.), then dump it to a
    dict and let the caller override.
    """
    from pymatgen.io.vasp.sets import MPRelaxSet

    vis = MPRelaxSet(structure, force_gamma=traits.gamma_required)
    incar = dict(vis.incar)

    # Apply atomate2 auto_ismear unless calc-type overrides
    ismear, sigma = sd.auto_ismear(is_metal=traits.is_metal_guess)
    incar.setdefault("ISMEAR", ismear)
    incar.setdefault("SIGMA", sigma)

    # Spin polarisation if any 3d/4f magnetic element is present
    if traits.magnetic_elements:
        incar["ISPIN"] = 2

    # LREAL=Auto only pays off for >20 atoms; small cells keep reciprocal projectors.
    if traits.n_atoms < 20:
        incar.pop("LREAL", None)
    elif traits.n_atoms > 60:
        incar["LREAL"] = "Auto"

    # NCORE — VASP wiki recommendation: sqrt(n_cores). Conservative default 4.
    incar.setdefault("NCORE", 4)

    return incar
