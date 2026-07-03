"""
SlabTransform - 表面切割变换器
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from modeling.transforms.base import BaseTransform
from modeling.tools.ase_tools import ASETools

if TYPE_CHECKING:
    from modeling.core.structure import Structure


class SlabTransform(BaseTransform):
    """
    表面切割变换器

    从晶体结构切割出特定密勒指数的表面。

    Parameters:
        miller: 密勒指数 (h, k, l)
        layers: 原子层数（默认 4）
        vacuum: 真空层厚度 (Å)，None 表示不在切割时添加（推荐用 VacuumTransform 单独控制）
        periodic: 是否周期性 (a, b 方向，默认 True)
    """

    name = "slab"
    required_params = ["miller"]
    default_params = {
        "layers": 4,
        "vacuum": None,
        "periodic": True,
    }

    def apply(self, structure: "Structure") -> "Structure":
        ASETools.require_ase()
        from ase.build import surface

        miller = tuple(int(x) for x in self.params["miller"])
        layers = int(self.params["layers"])
        vacuum = self.params["vacuum"]
        periodic = bool(self.params["periodic"])

        atoms = ASETools.to_ase_atoms(structure)
        slab = surface(
            atoms,
            indices=miller,
            layers=layers,
            vacuum=vacuum,
            periodic=periodic,
        )

        tag = f"{miller[0]}{miller[1]}{miller[2]}"
        new_struct = ASETools.from_ase_atoms(
            slab, name=f"{structure.name}_slab_{tag}"
        )
        # slab 默认 a/b 周期、c 非周期（vacuum 决定）
        new_struct.pbc = [True, True, vacuum is not None]
        return new_struct
