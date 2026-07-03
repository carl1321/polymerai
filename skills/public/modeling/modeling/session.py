"""
ModelingSession - 建模会话

用户交互的主入口
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, Optional, List, Union

from modeling.core.structure import Structure
from modeling.core.molecule import MoleculeInfo
from modeling.core.box import Box
from modeling.builders import BoxBuilder, Filler, Assembler, BulkBuilder, MoleculeBuilder
from modeling.validators import (
    ValidationReport,
    GeometryValidator,
    ChemistryValidator,
    PhysicsValidator,
)
from modeling.io import read_structure, write_structure


class ModelingSession:
    """
    建模会话

    管理一次建模任务的完整生命周期

    Example:
        >>> session = ModelingSession()
        >>> session.load_molecule("protein.pdb", "protein")
        >>> session.create_box(8.0)
        >>> session.place("protein", at="center")
        >>> session.fill_with_water()
        >>> report = session.validate()
        >>> session.export("output.pdb")
    """

    def __init__(self):
        """初始化会话"""
        # 已加载的分子
        self._molecules: Dict[str, Structure] = {}
        self._molecule_info: Dict[str, MoleculeInfo] = {}

        # 盒子
        self._box: Optional[Box] = None

        # 组装器
        self._assembler = Assembler()

        # 最终结构
        self._structure: Optional[Structure] = None

        # 验证器
        self._validators = [
            GeometryValidator(),
            ChemistryValidator(),
            PhysicsValidator(),
        ]

    # ==================== 分子管理 ====================

    def load_molecule(self, filepath: str, name: Optional[str] = None) -> MoleculeInfo:
        """
        加载分子文件

        Args:
            filepath: 文件路径
            name: 分子名称，默认使用文件名

        Returns:
            MoleculeInfo对象
        """
        structure = read_structure(filepath)

        if name is None:
            name = Path(filepath).stem

        structure.name = name
        self._molecules[name] = structure

        info = MoleculeInfo.from_structure(structure, name)
        self._molecule_info[name] = info

        return info

    def list_molecules(self) -> List[str]:
        """列出已加载的分子"""
        return list(self._molecules.keys())

    def get_molecule_info(self, name: str) -> Optional[MoleculeInfo]:
        """获取分子信息"""
        return self._molecule_info.get(name)

    # ==================== 构建操作 ====================

    def create_box(
        self,
        size: Union[float, tuple],
        pbc: tuple = (True, True, True)
    ) -> Box:
        """
        创建模拟盒子

        Args:
            size: 盒子尺寸 (nm)，单值为立方盒子
            pbc: 周期性边界条件

        Returns:
            Box对象
        """
        self._box = BoxBuilder.create_box_info(size, pbc=pbc)
        self._assembler.set_box(self._box)
        return self._box

    def place(
        self,
        molecule_name: str,
        at: str = "center",
        position: Optional[tuple] = None
    ) -> ModelingSession:
        """
        放置分子

        Args:
            molecule_name: 分子名称
            at: 放置位置 ("center", "origin", "absolute")
            position: 绝对位置 (nm)，用于at="absolute"

        Returns:
            self，支持链式调用
        """
        if molecule_name not in self._molecules:
            raise ValueError(f"未找到分子: {molecule_name}")

        structure = self._molecules[molecule_name]
        self._assembler.add(structure, placement=at, position=position, name=molecule_name)

        return self

    def create_nanotube(
        self,
        diameter: Optional[float] = None,
        n: Optional[int] = None,
        m: Optional[int] = None,
        length: Optional[float] = None,
        name: str = "nanotube"
    ) -> ModelingSession:
        """
        创建碳纳米管

        Args:
            diameter: 目标直径 (nm)
            n, m: 手性指数 (与diameter二选一)
            length: 长度 (nm)，默认为盒子z方向长度
            name: 名称

        Returns:
            self

        TODO: 使用 ASE 实现纳米管构建
        """
        from modeling.tools.ase_tools import ASETools

        if length is None and self._box is not None:
            length = self._box.size[2]

        length_angstrom = (length or 5.0) * 10.0  # nm -> Å

        # 确定手性指数
        if n is None or m is None:
            if diameter is None:
                raise ValueError("必须提供 (n, m) 或 diameter")
            # 简单估算：armchair (n,n)，直径 ≈ 0.0783 * n nm
            n = int(round(diameter / 0.0783))
            m = n

        # 使用 ASE 构建
        if ASETools.is_available():
            structure = ASETools.build_nanotube(n, m, length=1, bond=1.42)
            structure.name = name
        else:
            # 占位实现
            import numpy as np
            structure = Structure(
                positions=np.zeros((0, 3)),
                symbols=[],
                name=name,
            )

        self._molecules[name] = structure
        return self

    # ==================== 填充操作 ====================

    def fill_with_water(self, exclude: Optional[List[str]] = None) -> ModelingSession:
        """
        用水填充盒子

        Args:
            exclude: 要排除的区域/分子名称

        Returns:
            self

        TODO: 实现水填充
        """
        # 占位实现
        return self

    # ==================== 组装与验证 ====================

    def assemble(self) -> Structure:
        """
        组装最终结构

        Returns:
            组装后的Structure
        """
        self._structure = self._assembler.assemble()
        return self._structure

    def validate(self, levels: List[int] = [1, 2, 3]) -> ValidationReport:
        """
        验证结构

        Args:
            levels: 要执行的验证级别

        Returns:
            ValidationReport
        """
        if self._structure is None:
            self._structure = self.assemble()

        report = ValidationReport(structure_name=self._structure.name)

        for validator in self._validators:
            if validator.level in levels:
                result = validator.validate(self._structure)
                report.add_result(result)

        return report

    # ==================== 导出 ====================

    def export(self, filepath: str, format: Optional[str] = None):
        """
        导出结构

        Args:
            filepath: 输出路径
            format: 文件格式
        """
        if self._structure is None:
            self._structure = self.assemble()

        write_structure(self._structure, filepath, format)

    def export_report(self, filepath: str):
        """
        导出验证报告

        Args:
            filepath: 输出路径
        """
        report = self.validate()
        Path(filepath).write_text(report.to_markdown(), encoding='utf-8')

    # ==================== 属性 ====================

    @property
    def box(self) -> Optional[Box]:
        """当前盒子"""
        return self._box

    @property
    def structure(self) -> Optional[Structure]:
        """当前结构"""
        return self._structure

    def __repr__(self) -> str:
        n_mol = len(self._molecules)
        box_info = f"box={self._box.size}nm" if self._box else "no box"
        return f"ModelingSession(molecules={n_mol}, {box_info})"
