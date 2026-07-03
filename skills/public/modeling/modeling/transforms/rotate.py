"""
RotateTransform - 旋转变换器
"""

from __future__ import annotations
from typing import Tuple, Optional, Union, TYPE_CHECKING
import numpy as np

from modeling.transforms.base import BaseTransform

if TYPE_CHECKING:
    from modeling.core.structure import Structure


class RotateTransform(BaseTransform):
    """
    旋转变换器

    旋转结构

    Parameters:
        angle: 旋转角度 (度)
        axis: 旋转轴
            - str: "x", "y", "z"
            - (vx, vy, vz): 任意轴向量
        center: 旋转中心
            - str: "origin", "com" (质心), "cop" (几何中心)
            - (x, y, z): 指定坐标
    """

    name = "rotate"
    required_params = ["angle", "axis"]
    default_params = {
        "center": "com",
    }

    def apply(self, structure: "Structure") -> "Structure":
        """
        旋转结构

        Args:
            structure: 输入结构

        Returns:
            旋转后的结构
        """
        if structure.n_atoms == 0:
            return structure

        angle = self.params["angle"]
        axis = self.params["axis"]
        center = self.params["center"]

        # 转换角度为弧度
        angle_rad = np.radians(angle)

        # 确定旋转轴
        if isinstance(axis, str):
            axis_map = {
                "x": np.array([1, 0, 0]),
                "y": np.array([0, 1, 0]),
                "z": np.array([0, 0, 1]),
            }
            axis_vec = axis_map[axis.lower()]
        else:
            axis_vec = np.array(axis, dtype=float)
            axis_vec = axis_vec / np.linalg.norm(axis_vec)

        # 确定旋转中心
        if center == "origin":
            center_point = np.zeros(3)
        elif center == "com":
            center_point = structure.center_of_mass
        elif center == "cop":
            center_point = structure.positions.mean(axis=0)
        else:
            center_point = np.array(center, dtype=float)

        # 构建旋转矩阵 (Rodrigues' rotation formula)
        rotation_matrix = self._rotation_matrix(axis_vec, angle_rad)

        # 应用旋转
        positions = structure.positions - center_point
        new_positions = positions @ rotation_matrix.T
        new_positions = new_positions + center_point

        return structure._copy_with(positions=new_positions)

    @staticmethod
    def _rotation_matrix(axis: np.ndarray, angle: float) -> np.ndarray:
        """
        计算旋转矩阵 (Rodrigues' formula)

        Args:
            axis: 单位旋转轴
            angle: 旋转角度 (弧度)

        Returns:
            3x3 旋转矩阵
        """
        c = np.cos(angle)
        s = np.sin(angle)
        t = 1 - c

        x, y, z = axis

        return np.array([
            [t*x*x + c,   t*x*y - s*z, t*x*z + s*y],
            [t*x*y + s*z, t*y*y + c,   t*y*z - s*x],
            [t*x*z - s*y, t*y*z + s*x, t*z*z + c  ],
        ])

    @staticmethod
    def align_vector_rotation(v_from: np.ndarray, v_to: np.ndarray) -> np.ndarray:
        """
        计算将 v_from 旋转到 v_to 的 3x3 旋转矩阵

        处理退化情况 (平行/反平行向量)。

        Args:
            v_from: 源方向 (会被归一化)
            v_to: 目标方向 (会被归一化)

        Returns:
            3x3 旋转矩阵 R, 满足 R @ v_from_hat ≈ v_to_hat
        """
        a = np.array(v_from, dtype=float)
        b = np.array(v_to, dtype=float)
        a = a / np.linalg.norm(a)
        b = b / np.linalg.norm(b)

        cross = np.cross(a, b)
        cross_norm = np.linalg.norm(cross)
        dot = np.dot(a, b)

        if cross_norm < 1e-10:
            if dot > 0:
                # 平行 → 单位矩阵
                return np.eye(3)
            else:
                # 反平行 → 绕任意垂直轴旋转 180°
                perp = np.array([1.0, 0.0, 0.0])
                if abs(np.dot(a, perp)) > 0.9:
                    perp = np.array([0.0, 1.0, 0.0])
                perp = perp - np.dot(perp, a) * a
                perp = perp / np.linalg.norm(perp)
                return RotateTransform._rotation_matrix(perp, np.pi)

        axis = cross / cross_norm
        angle = np.arccos(np.clip(dot, -1.0, 1.0))
        return RotateTransform._rotation_matrix(axis, angle)
