"""
PyXtal 工具封装

基于空间群的随机晶体结构生成
"""

from __future__ import annotations
from typing import Optional, List, Union, Tuple, TYPE_CHECKING
import numpy as np

from modeling.core.structure import Structure

if TYPE_CHECKING:
    pass


class PyXtalTools:
    """
    PyXtal 工具封装

    PyXtal 是一个基于空间群对称性的随机晶体结构生成库

    功能:
    - 随机晶体生成 (原子晶体、分子晶体)
    - 空间群操作
    - 对称性分析
    - Wyckoff 位置处理

    参考: https://pyxtal.readthedocs.io/
    """

    _pyxtal_available: Optional[bool] = None

    @classmethod
    def is_available(cls) -> bool:
        """检查 PyXtal 是否可用"""
        if cls._pyxtal_available is None:
            try:
                import pyxtal
                cls._pyxtal_available = True
            except ImportError:
                cls._pyxtal_available = False
        return cls._pyxtal_available

    @classmethod
    def require_pyxtal(cls):
        """确保 PyXtal 可用"""
        if not cls.is_available():
            raise ImportError(
                "此功能需要 PyXtal。请安装: pip install pyxtal"
            )

    # ==================== 随机晶体生成 ====================

    @classmethod
    def random_crystal(
        cls,
        space_group: int,
        species: List[str],
        num_ions: List[int],
        factor: float = 1.0,
        lattice: Optional[List[float]] = None,
        sites: Optional[List[str]] = None,
    ) -> Structure:
        """
        生成随机晶体结构

        Args:
            space_group: 空间群编号 (1-230)
            species: 元素列表，如 ["Na", "Cl"]
            num_ions: 各元素数量，如 [4, 4]
            factor: 体积因子，用于调整密度
            lattice: 晶格参数 [a, b, c, alpha, beta, gamma]，None 则自动生成
            sites: Wyckoff 位置列表，None 则自动选择

        Returns:
            随机生成的晶体 Structure

        Example:
            >>> structure = PyXtalTools.random_crystal(
            ...     space_group=225,  # Fm-3m
            ...     species=["Na", "Cl"],
            ...     num_ions=[4, 4]
            ... )
        """
        cls.require_pyxtal()
        from pyxtal import pyxtal

        crystal = pyxtal()
        crystal.from_random(
            dim=3,
            group=space_group,
            species=species,
            numIons=num_ions,
            factor=factor,
            lattice=lattice,
            sites=sites,
        )

        return cls._pyxtal_to_structure(crystal)

    @classmethod
    def random_crystal_2d(
        cls,
        layer_group: int,
        species: List[str],
        num_ions: List[int],
        thickness: float = 0.0,
        factor: float = 1.0,
    ) -> Structure:
        """
        生成随机 2D 层状晶体

        Args:
            layer_group: 层群编号 (1-80)
            species: 元素列表
            num_ions: 各元素数量
            thickness: 层厚度 (Å)
            factor: 体积因子

        Returns:
            2D 晶体 Structure
        """
        cls.require_pyxtal()
        from pyxtal import pyxtal

        crystal = pyxtal()
        crystal.from_random(
            dim=2,
            group=layer_group,
            species=species,
            numIons=num_ions,
            thickness=thickness,
            factor=factor,
        )

        return cls._pyxtal_to_structure(crystal)

    @classmethod
    def random_molecular_crystal(
        cls,
        space_group: int,
        molecules: List[str],
        num_mols: List[int],
        factor: float = 1.0,
    ) -> Structure:
        """
        生成随机分子晶体

        Args:
            space_group: 空间群编号
            molecules: 分子列表 (SMILES 或分子名)
            num_mols: 各分子数量
            factor: 体积因子

        Returns:
            分子晶体 Structure

        TODO: 实现分子晶体生成
        """
        cls.require_pyxtal()
        from pyxtal import pyxtal

        crystal = pyxtal(molecular=True)
        crystal.from_random(
            dim=3,
            group=space_group,
            species=molecules,
            numIons=num_mols,
            factor=factor,
        )

        return cls._pyxtal_to_structure(crystal)

    # ==================== 对称性分析 ====================

    @classmethod
    def get_symmetry(cls, structure: Structure, symprec: float = 0.01) -> dict:
        """
        分析结构的对称性

        Args:
            structure: 输入结构
            symprec: 对称性精度

        Returns:
            包含空间群信息的字典
        """
        cls.require_pyxtal()
        from pyxtal import pyxtal

        crystal = cls._structure_to_pyxtal(structure)

        return {
            "space_group_number": crystal.group.number,
            "space_group_symbol": crystal.group.symbol,
            "point_group": str(crystal.group.point_group),
            "lattice_type": crystal.group.lattice_type,
        }

    # ==================== 转换函数 ====================

    @classmethod
    def _pyxtal_to_structure(cls, crystal) -> Structure:
        """将 PyXtal 对象转换为 Structure"""
        # 获取 ASE Atoms 对象
        atoms = crystal.to_ase()

        return Structure(
            positions=atoms.get_positions(),
            symbols=list(atoms.get_chemical_symbols()),
            cell=atoms.get_cell()[:],
            pbc=list(atoms.get_pbc()),
            name=f"pyxtal_{crystal.group.symbol}",
            properties={
                "space_group": crystal.group.number,
                "space_group_symbol": crystal.group.symbol,
            }
        )

    @classmethod
    def _structure_to_pyxtal(cls, structure: Structure):
        """将 Structure 转换为 PyXtal 对象"""
        cls.require_pyxtal()
        from pyxtal import pyxtal

        # 通过 ASE 转换
        from modeling.tools.ase_tools import ASETools
        atoms = ASETools.to_ase_atoms(structure)

        crystal = pyxtal()
        crystal.from_seed(atoms)

        return crystal

    # ==================== 空间群工具 ====================

    @classmethod
    def list_wyckoff_positions(cls, space_group: int) -> List[dict]:
        """
        列出空间群的所有 Wyckoff 位置

        Args:
            space_group: 空间群编号

        Returns:
            Wyckoff 位置列表
        """
        cls.require_pyxtal()
        from pyxtal.symmetry import Group

        group = Group(space_group)
        positions = []

        for wp in group:
            positions.append({
                "letter": wp.letter,
                "multiplicity": wp.multiplicity,
                "site_symmetry": wp.site_symm,
            })

        return positions

    @classmethod
    def get_compatible_space_groups(
        cls,
        species: List[str],
        num_ions: List[int]
    ) -> List[int]:
        """
        获取与给定化学计量比兼容的空间群

        Args:
            species: 元素列表
            num_ions: 各元素数量

        Returns:
            兼容的空间群编号列表

        TODO: 实现兼容性检查
        """
        cls.require_pyxtal()
        # 占位实现
        return list(range(1, 231))
