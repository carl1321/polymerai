"""
ChemistryValidator - 化学验证器

Level 2 验证，建议通过
"""

from __future__ import annotations
from typing import Dict, Tuple, Optional
import numpy as np

from modeling.validators.base import BaseValidator, ValidationResult
from modeling.core.structure import Structure


# 标准共价半径 (Å)
COVALENT_RADII: Dict[str, float] = {
    'H': 0.31, 'C': 0.76, 'N': 0.71, 'O': 0.66, 'F': 0.57,
    'P': 1.07, 'S': 1.05, 'Cl': 1.02, 'Br': 1.20, 'I': 1.39,
    'Si': 1.11, 'Fe': 1.32, 'Cu': 1.32, 'Zn': 1.22, 'Na': 1.66,
    'K': 2.03, 'Ca': 1.76, 'Mg': 1.41,
}

# 标准键长范围 (Å)
BOND_LENGTH_RANGES: Dict[Tuple[str, str], Tuple[float, float]] = {
    ('C', 'C'): (1.20, 1.60),
    ('C', 'H'): (1.06, 1.12),
    ('C', 'O'): (1.15, 1.50),
    ('C', 'N'): (1.15, 1.50),
    ('O', 'H'): (0.94, 1.00),
    ('N', 'H'): (0.98, 1.05),
    ('C', 'F'): (1.30, 1.40),
    ('C', 'Cl'): (1.72, 1.82),
}


class ChemistryValidator(BaseValidator):
    """
    化学验证器

    检查:
    - 键长合理性
    - 配位数
    - 电荷平衡
    """

    name = "chemistry"
    level = 2  # 建议通过

    def __init__(
        self,
        bond_tolerance: float = 0.15,
        check_bonds: bool = True,
        check_charges: bool = True
    ):
        """
        Args:
            bond_tolerance: 键长容差，相对于标准值
            check_bonds: 是否检查键长
            check_charges: 是否检查电荷
        """
        self.bond_tolerance = bond_tolerance
        self.check_bonds = check_bonds
        self.check_charges = check_charges

    def validate(self, structure: Structure, **kwargs) -> ValidationResult:
        """
        执行化学验证

        Args:
            structure: 要验证的结构

        Returns:
            ValidationResult
        """
        result = ValidationResult(name=self.name, passed=True)

        if structure.n_atoms == 0:
            return result

        # 记录化学式
        result.metrics["formula"] = structure.formula

        # 检查键长
        if self.check_bonds:
            self._check_bond_lengths(structure, result)

        # 检查电荷
        if self.check_charges and structure.charges is not None:
            self._check_charge_balance(structure, result)

        return result

    def _check_bond_lengths(self, structure: Structure, result: ValidationResult):
        """检查键长合理性"""
        unusual_bonds = []

        if structure.bonds is not None:
            # 使用已有的键信息
            for i, j in structure.bonds:
                dist = np.linalg.norm(
                    structure.positions[i] - structure.positions[j]
                )
                el1, el2 = sorted([structure.symbols[i], structure.symbols[j]])
                expected = BOND_LENGTH_RANGES.get((el1, el2))

                if expected:
                    if dist < expected[0] * (1 - self.bond_tolerance):
                        unusual_bonds.append((i, j, dist, "too_short"))
                    elif dist > expected[1] * (1 + self.bond_tolerance):
                        unusual_bonds.append((i, j, dist, "too_long"))

        result.metrics["unusual_bonds"] = len(unusual_bonds)

        if unusual_bonds:
            result.add_warning(
                code="bond_length",
                message=f"发现 {len(unusual_bonds)} 个异常键长",
                details={"bonds": unusual_bonds[:5]},
                suggestion="检查结构是否正确或需要优化"
            )

    def _check_charge_balance(self, structure: Structure, result: ValidationResult):
        """检查电荷平衡"""
        total_charge = structure.charges.sum()
        result.metrics["total_charge"] = float(total_charge)

        if abs(total_charge) > 0.01:
            result.add_info(
                code="charge",
                message=f"体系总电荷: {total_charge:.2f}",
                suggestion="如非预期，请检查离子添加是否正确"
            )
