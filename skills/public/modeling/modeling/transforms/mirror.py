"""
MirrorTransform - 镜像变换器
"""

from __future__ import annotations
from typing import Union, TYPE_CHECKING
import numpy as np

from modeling.transforms.base import BaseTransform

if TYPE_CHECKING:
    from modeling.core.structure import Structure


class MirrorTransform(BaseTransform):
    """
    镜像变换器

    镜像结构

    Parameters:
        plane: 镜像平面
            - str: "xy", "xz", "yz"
            - (a, b, c, d): 平面方程 ax + by + cz = d
        center: 镜像中心
            - str: "origin", "com"
            - (x, y, z): 指定坐标
    """

    name = "mirror"
    required_params = ["plane"]
    default_params = {
        "center": "origin",
    }

    def apply(self, structure: "Structure") -> "Structure":
        """
        镜像结构

        Args:
            structure: 输入结构

        Returns:
            镜像后的结构
        """
        if structure.n_atoms == 0:
            return structure

        plane = self.params["plane"]
        center = self.params["center"]

        # 确定镜像中心
        if center == "origin":
            center_point = np.zeros(3)
        elif center == "com":
            center_point = structure.center_of_mass
        else:
            center_point = np.array(center, dtype=float)

        # 相对于中心点的坐标
        positions = structure.positions - center_point

        # 应用镜像
        if isinstance(plane, str):
            if plane == "xy":
                positions[:, 2] = -positions[:, 2]
            elif plane == "xz":
                positions[:, 1] = -positions[:, 1]
            elif plane == "yz":
                positions[:, 0] = -positions[:, 0]
            else:
                raise ValueError(f"未知平面: {plane}")
        else:
            # 一般平面镜像
            # TODO: 实现一般平面的镜像变换
            raise NotImplementedError("一般平面镜像尚未实现")

        new_positions = positions + center_point

        return structure._copy_with(positions=new_positions)
