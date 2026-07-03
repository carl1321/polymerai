"""
MoleculeInfo - 分子信息类

从用户上传文件中提取的分子信息
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np


@dataclass
class MoleculeInfo:
    """
    分子信息数据类

    从用户上传的分子文件中提取的元信息，
    用于建模前的约束检查

    Attributes:
        name: 分子名称/标识
        n_atoms: 原子数
        formula: 分子式
        bbox_size: 包围盒尺寸 (dx, dy, dz)，单位 nm
        radius_of_gyration: 回旋半径，单位 nm
        total_charge: 总电荷
        file_format: 源文件格式
        has_bonds: 是否包含键信息
        has_charges: 是否包含电荷信息
    """

    name: str
    n_atoms: int
    formula: str
    bbox_size: Tuple[float, float, float]  # nm
    radius_of_gyration: float = 0.0  # nm
    total_charge: float = 0.0
    file_format: str = ""
    has_bonds: bool = False
    has_charges: bool = False
    source_file: str = ""

    @property
    def min_dimension(self) -> float:
        """最小维度 (nm)"""
        return min(self.bbox_size)

    @property
    def max_dimension(self) -> float:
        """最大维度 (nm)"""
        return max(self.bbox_size)

    @property
    def approximate_volume(self) -> float:
        """近似体积 (nm³)"""
        return np.prod(self.bbox_size)

    def can_fit_in(self, container_size: float, margin: float = 0.5) -> bool:
        """
        检查分子是否能放入容器

        Args:
            container_size: 容器尺寸 (nm)
            margin: 边缘余量 (nm)

        Returns:
            是否能放入
        """
        return self.max_dimension < (container_size - 2 * margin)

    def can_fit_through(self, opening_diameter: float) -> bool:
        """
        检查分子是否能通过开口

        Args:
            opening_diameter: 开口直径 (nm)

        Returns:
            是否能通过
        """
        return self.min_dimension < opening_diameter

    @classmethod
    def from_structure(cls, structure, name: str = "") -> MoleculeInfo:
        """
        从Structure对象创建MoleculeInfo

        Args:
            structure: Structure对象
            name: 分子名称

        Returns:
            MoleculeInfo对象
        """
        # 转换为nm
        bbox_nm = tuple(structure.bbox / 10.0)  # Å -> nm

        return cls(
            name=name or structure.name,
            n_atoms=structure.n_atoms,
            formula=structure.formula,
            bbox_size=bbox_nm,
            total_charge=structure.charges.sum() if structure.charges is not None else 0.0,
            has_bonds=structure.bonds is not None,
            has_charges=structure.charges is not None,
            source_file=structure.source_file,
        )

    def __repr__(self) -> str:
        return (f"MoleculeInfo(name='{self.name}', formula='{self.formula}', "
                f"size={self.bbox_size}nm, n_atoms={self.n_atoms})")
