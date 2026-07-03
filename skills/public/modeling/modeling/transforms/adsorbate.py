"""
AdsorbateTransform - 吸附物添加变换器
"""

from __future__ import annotations
from typing import TYPE_CHECKING

import numpy as np

from modeling.transforms.base import BaseTransform
from modeling.tools.ase_tools import ASETools

if TYPE_CHECKING:
    from modeling.core.structure import Structure


class AdsorbateTransform(BaseTransform):
    """
    吸附物添加变换器

    在表面 slab 上方放置分子。

    Parameters:
        molecule: 吸附分子
            - str: 名称（先查 BuiltinMolecules，再查 ase.build.molecule）
            - Structure: 直接使用
        site: 吸附位点
            - str: "top" / "bridge" / "fcc" / "hcp" / "hollow"
                   首选 slab.info["adsorbate_info"]（由 fcc111 等工厂注入）；
                   缺失时 fallback 为 ab 平面中心。
            - (x, y): 直接给出 ab 面坐标 (Å)
        height: 吸附高度 (Å)，相对 slab 顶层
        position: 与 site 二选一，直接 (x, y) 坐标 (Å)
        mol_index: 吸附物中作为锚点的原子索引
    """

    name = "adsorbate"
    required_params = ["molecule"]
    default_params = {
        "site": "top",
        "height": 2.0,
        "position": None,
        "mol_index": 0,
    }

    def apply(self, structure: "Structure") -> "Structure":
        ASETools.require_ase()
        from ase.build import add_adsorbate

        molecule = self._resolve_molecule(self.params["molecule"])
        adsorbate_atoms = ASETools.to_ase_atoms(molecule)

        slab = ASETools.to_ase_atoms(structure)
        height = float(self.params["height"])
        mol_index = int(self.params["mol_index"])

        position = self._resolve_position(slab)

        add_adsorbate(slab, adsorbate_atoms, height, position=position,
                      mol_index=mol_index)

        mol_name = molecule.name or "ads"
        site_tag = self.params["site"] if isinstance(self.params["site"], str) else "xy"
        return ASETools.from_ase_atoms(
            slab, name=f"{structure.name}_{mol_name}@{site_tag}"
        )

    def _resolve_molecule(self, molecule):
        if not isinstance(molecule, str):
            return molecule
        from modeling.resources.molecules import BuiltinMolecules
        try:
            return BuiltinMolecules.get(molecule)
        except KeyError:
            pass
        try:
            return ASETools.build_molecule(molecule)
        except Exception as e:
            raise ValueError(
                f"Unknown adsorbate '{molecule}'. Not in BuiltinMolecules "
                f"nor ase.build.molecule (g2 set). Error: {e}"
            )

    def _resolve_position(self, slab):
        position = self.params["position"]
        if position is not None:
            return (float(position[0]), float(position[1]))

        site = self.params["site"]
        if isinstance(site, (tuple, list)) and len(site) == 2:
            return (float(site[0]), float(site[1]))

        if isinstance(site, str):
            info = slab.info.get("adsorbate_info") if slab.info else None
            if info and "sites" in info and site in info["sites"]:
                return site
            cell = slab.get_cell()
            center = 0.5 * (cell[0, :2] + cell[1, :2])
            return (float(center[0]), float(center[1]))

        raise ValueError(f"Invalid site/position: site={site!r}, position={position!r}")
