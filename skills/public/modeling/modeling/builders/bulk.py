"""
BulkBuilder - 晶体结构构建器
"""

from __future__ import annotations
from typing import Optional

from modeling.builders.base import BaseBuilder
from modeling.core.structure import Structure
from modeling.tools.ase_tools import ASETools


class BulkBuilder(BaseBuilder):
    """
    晶体结构构建器

    创建晶体结构（体相材料）

    Parameters:
        element: 元素符号或化学式 (如 "Pt", "NaCl", "SiO2")
        crystalstructure: 晶体结构类型
            - "fcc", "bcc", "hcp", "diamond", "sc"
            - "rocksalt", "cesiumchloride", "zincblende", "wurtzite"
            - None: 自动检测
        a: 晶格常数 (Å)，None 使用默认值
        c: c轴晶格常数 (Å)，用于 hcp
        orthorhombic: 是否使用正交晶胞
        cubic: 是否使用立方晶胞
    """

    name = "bulk"
    required_params = ["element"]
    default_params = {
        "crystalstructure": None,
        "a": None,
        "c": None,
        "orthorhombic": False,
        "cubic": False,
    }

    def build(
        self,
        element: str,
        crystalstructure: Optional[str] = None,
        a: Optional[float] = None,
        c: Optional[float] = None,
        orthorhombic: bool = False,
        cubic: bool = False,
        **kwargs,
    ) -> Structure:
        ASETools.require_ase()
        from ase.build import bulk as ase_bulk

        kw = {}
        if crystalstructure is not None:
            kw["crystalstructure"] = crystalstructure
        if a is not None:
            kw["a"] = a
        if c is not None:
            kw["c"] = c
        if orthorhombic:
            kw["orthorhombic"] = True
        if cubic:
            kw["cubic"] = True

        atoms = ase_bulk(element, **kw)
        structure = ASETools.from_ase_atoms(atoms, name=f"bulk_{element}")
        structure.pbc = [True, True, True]
        return structure
