"""
TranslateTransform - 平移变换器
"""

from __future__ import annotations
from typing import Tuple, Union, TYPE_CHECKING
import numpy as np

from modeling.transforms.base import BaseTransform

if TYPE_CHECKING:
    from modeling.core.structure import Structure


class TranslateTransform(BaseTransform):
    """
    平移变换器

    平移结构

    Parameters:
        vector: 平移向量 (Å)
            - (dx, dy, dz): 平移量
        to: 目标位置，与 vector 二选一
            - str: "origin", "center" (移动质心到盒子中心)
            - (x, y, z): 移动质心到指定位置
    """

    name = "translate"
    required_params = []
    default_params = {
        "vector": None,
        "to": None,
    }

    def apply(self, structure: "Structure") -> "Structure":
        """
        平移结构

        Args:
            structure: 输入结构

        Returns:
            平移后的结构
        """
        if structure.n_atoms == 0:
            return structure

        vector = self.params.get("vector")
        to = self.params.get("to")

        if vector is not None:
            # 直接平移
            translation = np.array(vector, dtype=float)
        elif to is not None:
            # 移动到目标位置
            if to == "origin":
                target = np.zeros(3)
            elif to == "center":
                if structure.cell is None:
                    raise ValueError("center 需要盒子信息")
                cell = structure.cell
                if cell.ndim == 1:
                    target = cell / 2.0
                else:
                    target = np.diag(cell) / 2.0
            else:
                target = np.array(to, dtype=float)

            translation = target - structure.center_of_mass
        else:
            raise ValueError("必须提供 vector 或 to 参数")

        new_positions = structure.positions + translation

        return structure._copy_with(positions=new_positions)
