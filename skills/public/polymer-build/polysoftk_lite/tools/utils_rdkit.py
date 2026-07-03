"""Subset of pysoftk.tools.utils_rdkit — ``remove_plcholder`` only (PySoftK ``Lp``)."""

from __future__ import annotations

from rdkit import Chem
from rdkit import RDLogger

RDLogger.DisableLog("rdApp.*")


def remove_plcholder(mol: Chem.Mol, atom: str) -> Chem.Mol:
    """Replace placeholder atom symbols with hydrogen (same idea as upstream PySoftK)."""

    for atoms in mol.GetAtoms():
        if atoms.GetSymbol() == str(atom):
            mol.GetAtomWithIdx(atoms.GetIdx()).SetAtomicNum(1)

    Chem.SanitizeMol(mol)

    return mol
