"""
GeometryValidator - 几何验证器

Level 1 验证，必须通过
"""

from __future__ import annotations
from typing import List, Tuple, Optional
import numpy as np

from modeling.validators.base import BaseValidator, ValidationResult
from modeling.core.structure import Structure


class GeometryValidator(BaseValidator):
    """
    几何验证器

    检查:
    - 原子重叠
    - 边界溢出
    - 周期性镜像冲突
    """

    name = "geometry"
    level = 1  # 必须通过

    def __init__(
        self,
        overlap_threshold: float = 0.8,
        boundary_margin: float = 0.1
    ):
        """
        Args:
            overlap_threshold: 最小允许原子间距 (Å)
            boundary_margin: 边界余量 (Å)
        """
        self.overlap_threshold = overlap_threshold
        self.boundary_margin = boundary_margin

    def validate(self, structure: Structure, **kwargs) -> ValidationResult:
        """
        执行几何验证

        Args:
            structure: 要验证的结构

        Returns:
            ValidationResult
        """
        result = ValidationResult(name=self.name, passed=True)

        if structure.n_atoms == 0:
            result.add_info("empty", "结构为空")
            return result

        # 记录基本指标
        result.metrics["n_atoms"] = structure.n_atoms
        result.metrics["bbox"] = structure.bbox.tolist()

        # 检查原子重叠
        self._check_overlap(structure, result)

        # 检查边界
        if structure.cell is not None:
            self._check_boundary(structure, result)
            self._check_periodic_images(structure, result)

        return result

    def _check_overlap(self, structure: Structure, result: ValidationResult):
        """检查原子重叠"""
        overlaps = self.find_overlapping_atoms(
            structure.positions,
            self.overlap_threshold
        )

        result.metrics["n_overlaps"] = len(overlaps)

        if overlaps:
            result.add_error(
                code="overlap",
                message=f"发现 {len(overlaps)} 对重叠原子 (距离 < {self.overlap_threshold}Å)",
                details={"overlaps": overlaps[:10]},  # 只报告前10对
                suggestion="检查填充密度或分子放置位置"
            )

    def _check_boundary(self, structure: Structure, result: ValidationResult):
        """检查边界溢出"""
        positions = structure.positions
        cell = structure.cell

        if cell.ndim == 1:
            box_size = cell
        else:
            box_size = np.diag(cell)

        # 检查是否有原子超出盒子
        outside_min = (positions < -self.boundary_margin).any(axis=1)
        outside_max = (positions > box_size + self.boundary_margin).any(axis=0)

        n_outside = outside_min.sum() + outside_max.sum()
        result.metrics["n_outside_boundary"] = int(n_outside)

        if n_outside > 0:
            result.add_warning(
                code="boundary",
                message=f"{n_outside} 个原子超出盒子边界",
                suggestion="增大盒子尺寸或调整分子位置"
            )

    def _check_periodic_images(self, structure: Structure, result: ValidationResult):
        """检查周期性镜像冲突"""
        # TODO: 实现周期性镜像检查
        # 检查原子是否与其周期性镜像过近
        pass

    @staticmethod
    def find_overlapping_atoms(
        positions: np.ndarray,
        threshold: float
    ) -> List[Tuple[int, int, float]]:
        """
        查找重叠的原子对

        Args:
            positions: 原子坐标 (N, 3)
            threshold: 距离阈值 (Å)

        Returns:
            重叠原子对列表 [(i, j, distance), ...]
        """
        overlaps = []
        n = len(positions)

        # 简单实现，大体系需要优化 (如使用KD树)
        for i in range(n):
            for j in range(i + 1, n):
                dist = np.linalg.norm(positions[i] - positions[j])
                if dist < threshold:
                    overlaps.append((i, j, float(dist)))

        return overlaps
