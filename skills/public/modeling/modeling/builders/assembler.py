"""
Assembler - 结构组装器

将多个组件组装成最终结构
"""

from __future__ import annotations
from typing import List, Optional, Dict
import numpy as np

from modeling.core.structure import Structure, merge_structures
from modeling.core.component import Component, PlacementType
from modeling.core.box import Box


class Assembler:
    """
    结构组装器

    负责将多个组件按照放置规则组装成最终结构

    Features:
    - 坐标变换 (平移、旋转)
    - 组件放置 (居中、指定位置)
    - 冲突预检
    """

    def __init__(self, box: Optional[Box] = None):
        """
        初始化组装器

        Args:
            box: 模拟盒子
        """
        self.box = box
        self.components: List[Component] = []
        self._structures: List[Structure] = []

    def set_box(self, box: Box) -> Assembler:
        """设置盒子"""
        self.box = box
        return self

    def add(
        self,
        structure: Structure,
        placement: str = "center",
        position: Optional[tuple] = None,
        name: str = ""
    ) -> Assembler:
        """
        添加结构组件

        Args:
            structure: 要添加的结构
            placement: 放置方式 ("center", "origin", "absolute")
            position: 位置坐标 (nm)，用于absolute模式
            name: 组件名称

        Returns:
            self，支持链式调用
        """
        # 应用放置变换
        placed = self._apply_placement(structure, placement, position)
        placed.name = name or structure.name

        self._structures.append(placed)
        return self

    def _apply_placement(
        self,
        structure: Structure,
        placement: str,
        position: Optional[tuple]
    ) -> Structure:
        """
        应用放置变换

        Args:
            structure: 原始结构
            placement: 放置方式
            position: 位置坐标 (nm)

        Returns:
            变换后的结构
        """
        if structure.n_atoms == 0:
            return structure

        if placement == "center":
            if self.box is None:
                raise ValueError("居中放置需要先设置盒子")
            return structure.center_at(self.box.center_angstrom)

        elif placement == "origin":
            return structure.center_at(np.zeros(3))

        elif placement == "absolute":
            if position is None:
                raise ValueError("absolute放置需要提供position")
            pos_angstrom = np.array(position) * 10.0  # nm -> Å
            return structure.center_at(pos_angstrom)

        else:
            raise ValueError(f"未知的放置方式: {placement}")

    def assemble(self, name: str = "assembled") -> Structure:
        """
        组装所有组件

        Returns:
            组装后的完整结构
        """
        if not self._structures:
            return Structure.empty()

        # 合并所有结构
        result = merge_structures(self._structures, name=name)

        # 应用盒子参数
        if self.box is not None:
            result.cell = self.box.size_angstrom
            result.pbc = list(self.box.pbc)

        return result

    def clear(self) -> Assembler:
        """清除所有组件"""
        self.components.clear()
        self._structures.clear()
        return self

    def __repr__(self) -> str:
        return f"Assembler(n_components={len(self._structures)}, box={self.box})"
