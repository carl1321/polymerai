"""Subset of pysoftk.tools.utils_ob — force-field relaxation + rotor search (PySoftK ``Lp``)."""

from __future__ import annotations

import numpy as np
from openbabel import openbabel as ob
from openbabel import pybel as pb


def ff_ob_relaxation(
    mol: pb.Molecule,
    FF: str = "MMFF94",
    relax_iterations: int = 100,
    ff_thr: float = 1.0e-6,
) -> pb.Molecule:
    ff = ob.OBForceField.FindForceField(str(FF))
    ff.Setup(mol.OBMol)
    ff.ConjugateGradients(int(relax_iterations), float(ff_thr))
    ff.GetCoordinates(mol.OBMol)
    return mol


def rotor_opt(mol: pb.Molecule, FF: str = "MMFF94", rot_steps: int = 125) -> pb.Molecule:
    ff = ob.OBForceField.FindForceField(str(FF))
    ff.Setup(mol.OBMol)
    ff.FastRotorSearch()
    ff.WeightedRotorSearch(int(rot_steps), int(np.ceil(rot_steps / 2.0)))
    ff.GetCoordinates(mol.OBMol)
    return mol
