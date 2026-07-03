"""Vendored ``Lp`` from PySoftK linear polymer (subset)."""

from __future__ import annotations

import numpy as np
from openbabel import pybel as pb
from rdkit import Chem
from rdkit import RDLogger
from rdkit.Chem import rdDistGeom as molDG
from rdkit.Geometry import Point3D
from rdkit.Chem.rdMolTransforms import *

RDLogger.DisableLog("rdApp.*")

from polysoftk_lite.tools.utils_func import atom_neigh
from polysoftk_lite.tools.utils_ob import ff_ob_relaxation, rotor_opt
from polysoftk_lite.tools.utils_rdkit import remove_plcholder


class Lp:
    """
    A class for constructing linear polymers from individual molecular units (monomers)
    using RDKit functionalities.

    Vendored from PySoftK (see NOTICE in polysoftk_lite/).
    """

    __slots__ = ["mol", "atom", "n_copies", "shift"]

    def __init__(self, mol, atom, n_copies, shift):
        self.mol = mol
        self.atom = atom
        self.n_copies = n_copies
        self.shift = float(1.25) if shift is None else float(shift)

    def max_dist_mol(self):
        mol = self.mol
        bm = molDG.GetMoleculeBoundsMatrix(mol)
        return np.amax(bm)

    def x_shift(self):
        shift = self.shift
        shift_final = float(self.max_dist_mol()) - float(shift)

        return shift_final

    def copy_mol(self):
        mol = self.mol
        CanonicalizeConformer(mol.GetConformer())

        n_copies = self.n_copies

        fragments = [mol for _ in range(int(n_copies))]

        return fragments

    def polimerisation(self, fragments):
        x_offset = self.x_shift()

        outmol = fragments[0]
        for idx, values in enumerate(fragments[1:]):
            outmol = Chem.CombineMols(
                outmol, values, offset=Point3D(x_offset * (idx + 1), 0.0, 0.0)
            )

        order = Chem.CanonicalRankAtoms(outmol, includeChirality=True)
        Chem.RenumberAtoms(outmol, list(order))

        return outmol

    def bond_conn(self, outmol):
        atom = self.atom

        bonds = atom_neigh(outmol, str(atom))
        conn_bonds = [b for a, b in bonds][1:-1]

        erase_br = [a for a, b in bonds]
        all_conn = list(zip(conn_bonds[::2], conn_bonds[1::2]))

        return all_conn, erase_br

    def proto_polymer(self):
        atom = self.atom
        mol = self.mol
        n_copies = self.n_copies

        fragments = self.copy_mol()
        outmol = self.polimerisation(fragments)
        all_conn, erase_br = self.bond_conn(outmol)

        rwmol = Chem.RWMol(outmol)
        for ini, fin in all_conn:
            rwmol.AddBond(ini, fin, Chem.BondType.SINGLE)

        for i in sorted(erase_br[1:-1], key=None, reverse=True):
            rwmol.RemoveAtom(i)

        mol3 = rwmol.GetMol()
        Chem.SanitizeMol(mol3)

        mol4 = Chem.AddHs(mol3, addCoords=True)

        return mol4

    def linear_polymer(
        self,
        force_field="MMFF",
        relax_iterations=350,
        rot_steps=125,
        no_att=True,
    ):
        mol = self.proto_polymer()
        atom = self.atom

        if no_att:
            mol1 = remove_plcholder(mol, atom)
        else:
            mol1 = mol

        last_rdkit = Chem.MolToPDBBlock(mol1)
        mol_new = pb.readstring("pdb", last_rdkit)

        valid_force_fields = ("MMFF", "UFF", "MMFF94")
        if force_field not in valid_force_fields:
            raise ValueError(
                f"Invalid force field: {force_field}. Valid options are: {valid_force_fields}"
            )

        if force_field == "MMFF":
            force_field = "MMFF94"

        try:
            relax_iterations = int(relax_iterations)
            rot_steps = int(rot_steps)
        except ValueError:
            raise ValueError("relax_iterations and rot_steps must be integers.")

        last_mol = ff_ob_relaxation(mol_new, force_field, relax_iterations)
        rot_mol = rotor_opt(last_mol, force_field, rot_steps)

        return rot_mol
