"""Subset of pysoftk.tools.utils_func — ``atom_neigh`` only (PySoftK ``Lp``)."""

from __future__ import annotations

from rdkit import Chem
from rdkit import RDLogger

RDLogger.DisableLog("rdApp.*")


def atom_neigh(mol: Chem.Mol, atom: str) -> list[tuple[int, int]]:
    """Placeholder atoms of type ``atom`` and their direct neighbors (flattened pairs)."""

    neigh = []
    for atm_obj in mol.GetAtoms():
        if atm_obj.GetSymbol() == str(atom):
            for nbr in atm_obj.GetNeighbors():
                neigh.append((atm_obj.GetIdx(), nbr.GetIdx()))
    return neigh
