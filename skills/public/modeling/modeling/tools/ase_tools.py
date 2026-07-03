"""
ASE工具封装

封装ASE的常用功能
"""

from __future__ import annotations
from typing import Optional, TYPE_CHECKING
import numpy as np

from modeling.core.structure import Structure

# 延迟导入ASE
if TYPE_CHECKING:
    from ase import Atoms


class ASETools:
    """
    ASE工具封装

    提供ASE的常用功能，自动处理ASE未安装的情况
    """

    _ase_available: Optional[bool] = None

    @classmethod
    def is_available(cls) -> bool:
        """检查ASE是否可用"""
        if cls._ase_available is None:
            try:
                import ase
                cls._ase_available = True
            except ImportError:
                cls._ase_available = False
        return cls._ase_available

    @classmethod
    def require_ase(cls):
        """确保ASE可用，否则抛出异常"""
        if not cls.is_available():
            raise ImportError(
                "此功能需要ASE。请安装: pip install ase"
            )

    # ==================== 结构转换 ====================

    @classmethod
    def to_ase_atoms(cls, structure: Structure) -> "Atoms":
        """
        Structure转ASE Atoms

        Args:
            structure: Structure对象

        Returns:
            ASE Atoms对象
        """
        cls.require_ase()
        from ase import Atoms

        atoms = Atoms(
            symbols=structure.symbols,
            positions=structure.positions,
            cell=structure.cell,
            pbc=structure.pbc,
        )

        if structure.charges is not None:
            atoms.set_initial_charges(structure.charges)

        return atoms

    @classmethod
    def from_ase_atoms(cls, atoms: "Atoms", name: str = "") -> Structure:
        """
        ASE Atoms转Structure

        Args:
            atoms: ASE Atoms对象
            name: 结构名称

        Returns:
            Structure对象
        """
        charges = None
        if atoms.has('initial_charges'):
            charges = atoms.get_initial_charges()

        return Structure(
            positions=atoms.get_positions(),
            symbols=list(atoms.get_chemical_symbols()),
            cell=atoms.get_cell()[:] if atoms.cell.any() else None,
            pbc=list(atoms.get_pbc()),
            charges=charges,
            name=name,
        )

    # ==================== 结构构建 ====================

    @classmethod
    def build_nanotube(
        cls,
        n: int,
        m: int,
        length: int = 1,
        bond: float = 1.42,
        vacuum: Optional[float] = None
    ) -> Structure:
        """
        构建碳纳米管

        Args:
            n, m: 手性指数
            length: 重复单元数
            bond: C-C键长 (Å)
            vacuum: 真空层厚度 (Å)

        Returns:
            Structure
        """
        cls.require_ase()
        from ase.build import nanotube

        atoms = nanotube(n, m, length=length, bond=bond, vacuum=vacuum)
        return cls.from_ase_atoms(atoms, name=f"CNT({n},{m})")

    @classmethod
    def build_bulk(
        cls,
        name: str,
        crystalstructure: Optional[str] = None,
        a: Optional[float] = None,
        **kwargs
    ) -> Structure:
        """
        构建晶体结构

        Args:
            name: 元素名或化合物名
            crystalstructure: 晶体结构类型 (fcc, bcc, hcp, diamond等)
            a: 晶格常数 (Å)

        Returns:
            Structure
        """
        cls.require_ase()
        from ase.build import bulk

        atoms = bulk(name, crystalstructure=crystalstructure, a=a, **kwargs)
        return cls.from_ase_atoms(atoms, name=name)

    @classmethod
    def build_molecule(cls, name: str) -> Structure:
        """
        构建分子

        Args:
            name: 分子名 (H2O, CH4, CO2等)

        Returns:
            Structure
        """
        cls.require_ase()
        from ase.build import molecule

        atoms = molecule(name)
        return cls.from_ase_atoms(atoms, name=name)

    # ==================== 文件I/O ====================

    @classmethod
    def read_file(cls, filepath: str, format: Optional[str] = None) -> Structure:
        """
        使用ASE读取文件

        Args:
            filepath: 文件路径
            format: 文件格式

        Returns:
            Structure
        """
        cls.require_ase()
        from ase.io import read

        atoms = read(filepath, format=format)
        return cls.from_ase_atoms(atoms, name=filepath)

    @classmethod
    def write_file(
        cls,
        structure: Structure,
        filepath: str,
        format: Optional[str] = None
    ):
        """
        使用ASE写入文件

        Args:
            structure: Structure对象
            filepath: 文件路径
            format: 文件格式
        """
        cls.require_ase()
        from ase.io import write

        atoms = cls.to_ase_atoms(structure)
        write(filepath, atoms, format=format)
