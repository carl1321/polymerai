"""
VacuumTransform - 真空层添加变换器
"""

from __future__ import annotations
from typing import TYPE_CHECKING

import numpy as np

from modeling.transforms.base import BaseTransform
from modeling.tools.ase_tools import ASETools

if TYPE_CHECKING:
    from modeling.core.structure import Structure


class VacuumTransform(BaseTransform):
    """
    真空层添加变换器

    在结构周围添加真空层。

    实现说明：使用 ASE 的 add_vacuum，在指定 cell 方向上扩展 thickness Å，
    并把原子居中到该方向的中点（symmetric=True 时）。

    Parameters:
        thickness: 真空层厚度 (Å)
        axis: 添加方向 (0=a, 1=b, 2=c)，默认 2
        symmetric: 是否将 slab 在该方向居中（默认 True）
    """

    name = "vacuum"
    required_params = ["thickness"]
    default_params = {
        "axis": 2,
        "symmetric": True,
    }

    def apply(self, structure: "Structure") -> "Structure":
        ASETools.require_ase()
        from ase.build import add_vacuum

        thickness = float(self.params["thickness"])
        axis = int(self.params["axis"])
        symmetric = bool(self.params["symmetric"])

        atoms = ASETools.to_ase_atoms(structure)

        # add_vacuum 默认沿 c (axis=2) 方向扩展。对其他方向，先重排 cell。
        if axis == 2:
            add_vacuum(atoms, thickness)
        else:
            # 把目标轴换到 c，加完真空再换回来
            order = [0, 1, 2]
            order[axis], order[2] = order[2], order[axis]
            cell = atoms.get_cell()
            atoms.set_cell(cell[order], scale_atoms=False)
            atoms.set_positions(atoms.get_positions()[:, order])
            add_vacuum(atoms, thickness)
            cell = atoms.get_cell()
            atoms.set_cell(cell[order], scale_atoms=False)
            atoms.set_positions(atoms.get_positions()[:, order])

        if symmetric:
            pos = atoms.get_positions()
            cell_len = np.linalg.norm(atoms.get_cell()[axis])
            atoms_extent = pos[:, axis].max() - pos[:, axis].min()
            shift = (cell_len - atoms_extent) / 2 - pos[:, axis].min()
            pos[:, axis] += shift
            atoms.set_positions(pos)

        new_struct = ASETools.from_ase_atoms(
            atoms, name=f"{structure.name}_vacuum{thickness:g}A"
        )
        pbc = list(structure.pbc) if structure.pbc else [True, True, True]
        pbc[axis] = True
        new_struct.pbc = pbc
        return new_struct
