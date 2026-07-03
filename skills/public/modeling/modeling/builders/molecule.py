"""
MoleculeBuilder - 分子构建器
"""

from __future__ import annotations
from typing import Optional, Union, TYPE_CHECKING

from modeling.builders.base import BaseBuilder
from modeling.core.structure import Structure

if TYPE_CHECKING:
    pass


class MoleculeBuilder(BaseBuilder):
    """
    分子构建器

    创建分子结构

    Parameters:
        name: 分子名称
            - 内置分子: "water", "methane", "CO", "CO2", "H2O", "NH3"...
            - ASE 分子库中的分子
        source: 分子来源
            - "builtin": 从内置库获取
            - "ase": 从 ASE 分子库获取
            - "file": 从文件读取（此时 name 为文件路径）
    """

    name = "molecule"
    required_params = ["name"]
    default_params = {
        "source": "auto",  # auto, builtin, ase, file
    }

    def build(
        self,
        name: str,
        source: str = "auto",
        **kwargs
    ) -> Structure:
        """
        构建分子

        Args:
            name: 分子名称或文件路径
            source: 分子来源

        Returns:
            分子 Structure

        TODO: 实现分子构建
        """
        import numpy as np

        if source == "auto":
            # 自动检测来源
            source = self._detect_source(name)

        if source == "builtin":
            return self._from_builtin(name)
        elif source == "ase":
            return self._from_ase(name)
        elif source == "file":
            return self._from_file(name)
        else:
            raise ValueError(f"未知的分子来源: {source}")

    def _detect_source(self, name: str) -> str:
        """检测分子来源"""
        from pathlib import Path
        from modeling.resources.molecules import BuiltinMolecules

        # 检查是否是文件路径
        if Path(name).exists():
            return "file"

        # 检查是否在内置库中
        try:
            BuiltinMolecules.get(name)
            return "builtin"
        except KeyError:
            pass

        # 默认尝试 ASE
        return "ase"

    def _from_builtin(self, name: str) -> Structure:
        """从内置库获取"""
        from modeling.resources.molecules import BuiltinMolecules
        return BuiltinMolecules.get(name)

    def _from_ase(self, name: str) -> Structure:
        """从 ASE 分子库获取"""
        from modeling.tools.ase_tools import ASETools
        return ASETools.build_molecule(name)

    def _from_file(self, filepath: str) -> Structure:
        """从文件读取"""
        from modeling.io import read_structure
        return read_structure(filepath)
