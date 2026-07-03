"""
PhysicsValidator - 物理验证器

Level 3 验证，可选
"""

from __future__ import annotations
from typing import Optional
import numpy as np

from modeling.validators.base import BaseValidator, ValidationResult
from modeling.core.structure import Structure


# 元素原子质量 (amu)
ATOMIC_MASSES = {
    'H': 1.008, 'C': 12.011, 'N': 14.007, 'O': 15.999, 'F': 18.998,
    'P': 30.974, 'S': 32.065, 'Cl': 35.453, 'Br': 79.904, 'I': 126.90,
    'Si': 28.086, 'Fe': 55.845, 'Cu': 63.546, 'Zn': 65.38, 'Na': 22.990,
    'K': 39.098, 'Ca': 40.078, 'Mg': 24.305,
}

# 典型密度参考值 (g/cm³)
TYPICAL_DENSITIES = {
    'water': (0.95, 1.05),
    'organic': (0.7, 1.5),
    'protein': (1.2, 1.4),
    'lipid': (0.9, 1.1),
    'default': (0.5, 3.0),
}


class PhysicsValidator(BaseValidator):
    """
    物理验证器

    检查:
    - 密度合理性
    - 能量预检 (可选)
    """

    name = "physics"
    level = 3  # 可选

    def __init__(
        self,
        density_range: tuple = (0.5, 3.0),
        check_energy: bool = False
    ):
        """
        Args:
            density_range: 合理密度范围 (g/cm³)
            check_energy: 是否检查能量 (需要xTB)
        """
        self.density_range = density_range
        self.check_energy = check_energy

    def validate(self, structure: Structure, **kwargs) -> ValidationResult:
        """
        执行物理验证

        Args:
            structure: 要验证的结构

        Returns:
            ValidationResult
        """
        result = ValidationResult(name=self.name, passed=True)

        if structure.n_atoms == 0:
            return result

        # 检查密度
        if structure.cell is not None:
            self._check_density(structure, result)

        # 检查能量 (可选)
        if self.check_energy:
            self._check_energy(structure, result)

        return result

    def _check_density(self, structure: Structure, result: ValidationResult):
        """检查密度"""
        density = self.calculate_density(structure)

        if density is None:
            return

        result.metrics["density_g_cm3"] = round(density, 3)

        if density < self.density_range[0]:
            result.add_warning(
                code="density_low",
                message=f"密度偏低: {density:.2f} g/cm³",
                suggestion="可能需要增加填充分子数量"
            )
        elif density > self.density_range[1]:
            result.add_warning(
                code="density_high",
                message=f"密度偏高: {density:.2f} g/cm³",
                suggestion="可能需要减少填充分子或增大盒子"
            )

    def _check_energy(self, structure: Structure, result: ValidationResult):
        """
        能量预检 (使用xTB)

        TODO: 实现xTB调用
        """
        result.add_info(
            code="energy_skipped",
            message="能量检查已跳过 (xTB未安装)"
        )

    @staticmethod
    def calculate_density(structure: Structure) -> Optional[float]:
        """
        计算密度

        Args:
            structure: 结构

        Returns:
            密度 (g/cm³)，如无法计算返回None
        """
        if structure.cell is None:
            return None

        # 计算总质量 (amu)
        total_mass = 0.0
        for symbol in structure.symbols:
            mass = ATOMIC_MASSES.get(symbol, 0.0)
            if mass == 0.0:
                # 未知元素，尝试从周期表估算
                mass = 10.0  # 粗略估计
            total_mass += mass

        # 计算体积 (ų)
        cell = structure.cell
        if cell.ndim == 1:
            volume = np.prod(cell)
        else:
            volume = np.abs(np.linalg.det(cell))

        if volume == 0:
            return None

        # 转换为 g/cm³
        # 1 amu = 1.66054e-24 g
        # 1 Å³ = 1e-24 cm³
        density = (total_mass * 1.66054e-24) / (volume * 1e-24)

        return density
