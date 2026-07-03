"""
SupercellTransform - 超胞变换器
"""

from __future__ import annotations
from typing import TYPE_CHECKING

import numpy as np

from modeling.transforms.base import BaseTransform
from modeling.tools.ase_tools import ASETools

if TYPE_CHECKING:
    from modeling.core.structure import Structure


class SupercellTransform(BaseTransform):
    """
    超胞变换器

    Parameters:
        matrix: 超胞矩阵
            - (a, b, c): 对角超胞，各方向重复次数（int）
            - 3x3 矩阵: 一般超胞变换
    """

    name = "supercell"
    required_params = ["matrix"]
    default_params = {}

    def apply(self, structure: "Structure") -> "Structure":
        ASETools.require_ase()
        from ase.build import make_supercell

        matrix = self.params["matrix"]
        atoms = ASETools.to_ase_atoms(structure)

        arr = np.asarray(matrix)
        if arr.shape == (3,):
            new_atoms = atoms.repeat(tuple(int(x) for x in arr))
            tag = f"{int(arr[0])}x{int(arr[1])}x{int(arr[2])}"
        elif arr.shape == (3, 3):
            new_atoms = make_supercell(atoms, arr)
            tag = "custom"
        else:
            raise ValueError(
                f"supercell.matrix 必须是 (3,) 或 (3,3)，得到 shape={arr.shape}"
            )

        new_struct = ASETools.from_ase_atoms(
            new_atoms, name=f"{structure.name}_supercell_{tag}"
        )
        new_struct.pbc = list(structure.pbc)
        return new_struct
