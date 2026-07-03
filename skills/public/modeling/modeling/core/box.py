"""
Box - 模拟盒子类
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple, List
import numpy as np


@dataclass
class Box:
    """
    模拟盒子

    Attributes:
        size: 盒子尺寸 (lx, ly, lz)，单位 nm
        origin: 盒子原点，单位 nm
        pbc: 周期性边界条件
    """

    size: Tuple[float, float, float]  # nm
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # nm
    pbc: Tuple[bool, bool, bool] = (True, True, True)

    @property
    def size_angstrom(self) -> np.ndarray:
        """盒子尺寸 (Å)"""
        return np.array(self.size) * 10.0

    @property
    def origin_angstrom(self) -> np.ndarray:
        """原点位置 (Å)"""
        return np.array(self.origin) * 10.0

    @property
    def center(self) -> np.ndarray:
        """盒子中心 (nm)"""
        return np.array(self.origin) + np.array(self.size) / 2.0

    @property
    def center_angstrom(self) -> np.ndarray:
        """盒子中心 (Å)"""
        return self.center * 10.0

    @property
    def volume(self) -> float:
        """体积 (nm³)"""
        return np.prod(self.size)

    @property
    def volume_angstrom(self) -> float:
        """体积 (ų)"""
        return np.prod(self.size_angstrom)

    @classmethod
    def cubic(cls, length: float, **kwargs) -> Box:
        """
        创建立方盒子

        Args:
            length: 边长 (nm)
        """
        return cls(size=(length, length, length), **kwargs)

    @classmethod
    def from_structure(cls, structure, padding: float = 1.0) -> Box:
        """
        根据结构创建包围盒

        Args:
            structure: Structure对象
            padding: 边缘填充 (nm)
        """
        bbox = structure.bbox / 10.0  # Å -> nm
        size = tuple(bbox + 2 * padding)
        return cls(size=size)

    def contains(self, point_nm: np.ndarray) -> bool:
        """检查点是否在盒子内"""
        point = np.asarray(point_nm)
        origin = np.array(self.origin)
        end = origin + np.array(self.size)
        return np.all(point >= origin) and np.all(point <= end)

    def __repr__(self) -> str:
        return f"Box(size={self.size}nm, pbc={self.pbc})"
