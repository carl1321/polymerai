"""
CombinatorialBuilder - 组合枚举构建器

基于模板结构和替换基团列表，穷尽所有组合。
用于批量生成同类结构（如 SN2 反应的所有取代组合）。
"""

from __future__ import annotations
from typing import Dict, List, Any, Optional, Tuple
import itertools
import copy
import numpy as np

from modeling.builders.base import BaseBuilder
from modeling.core.structure import Structure


class CombinatorialBuilder(BaseBuilder):
    """
    组合枚举构建器

    给定模板结构（带标记的替换位点）和每个位点的候选片段列表，
    通过 itertools.product 穷尽所有组合，生成全部结构。

    用法:
        builder = CombinatorialBuilder()
        structures = builder.build_all(
            template=template_structure,
            substitutions={
                "R": ["CH3", "NO2", "F_fragment"],
                "Nu": ["F-", "Cl-", "Br-"],
                "LG": ["F-", "Cl-", "Br-"],
            },
        )

    模板约定:
        template.properties["substitution_sites"] = {
            "R": {
                "atom_index": 5,              # 占位原子索引
                "direction": [1.0, 0.0, 0.0], # 键方向 (从母体指向片段)
                "bond_length": 1.54,          # 键长 (Å)
            },
            ...
        }
    """

    name = "combinatorial"
    required_params = ["template", "substitutions"]
    default_params = {
        "naming_template": "{template}_{combo}",
    }

    def build(self, **params) -> Structure:
        """返回第一个组合 (BaseBuilder 接口兼容)"""
        results = self.build_all(**params)
        if not results:
            raise ValueError("没有生成任何组合")
        return results[0]

    def build_all(self, **params) -> List[Structure]:
        """
        生成所有组合的结构

        Args:
            template: 带替换位点标记的 Structure
            substitutions: {位点名: [片段名列表]}
            naming_template: 命名模板

        Returns:
            所有组合的 Structure 列表
        """
        params = self.validate_params(params)
        template = params["template"]
        substitutions = params["substitutions"]
        naming_tpl = params.get("naming_template", "{template}_{combo}")

        # 验证模板有替换位点
        sites = template.properties.get("substitution_sites", {})
        if not sites:
            raise ValueError("模板缺少 substitution_sites 信息")

        for site_name in substitutions:
            if site_name not in sites:
                raise ValueError(f"替换位点 '{site_name}' 不在模板中。可用: {list(sites.keys())}")

        # 生成所有组合
        combinations = self._generate_combinations(substitutions)
        results = []

        for combo in combinations:
            structure = self._apply_combination(template, sites, combo)

            # 命名
            combo_str = "_".join(f"{k}-{v}" for k, v in sorted(combo.items()))
            structure.name = naming_tpl.format(
                template=template.name or "structure",
                combo=combo_str,
            )

            # 记录组合信息
            structure.properties["combination"] = combo.copy()

            results.append(structure)

        return results

    def _generate_combinations(self, substitutions: Dict[str, List[str]]) -> List[Dict[str, str]]:
        """生成所有排列组合"""
        site_names = sorted(substitutions.keys())
        fragment_lists = [substitutions[name] for name in site_names]

        combinations = []
        for combo in itertools.product(*fragment_lists):
            combinations.append(dict(zip(site_names, combo)))

        return combinations

    def _apply_combination(
        self,
        template: Structure,
        sites: Dict[str, Dict],
        combo: Dict[str, str],
    ) -> Structure:
        """
        将一组替换应用到模板上

        对于每个替换位点，获取片段并放置到位点位置。
        """
        from modeling.resources.molecules import BuiltinMolecules

        # 深拷贝模板
        new_positions = template.positions.copy()
        new_symbols = list(template.symbols)
        new_properties = copy.deepcopy(template.properties)

        # 记录需要删除的占位原子 (从大到小排序，避免索引偏移)
        atoms_to_remove = []
        atoms_to_add_positions = []
        atoms_to_add_symbols = []

        for site_name, fragment_name in combo.items():
            site_info = sites[site_name]
            atom_idx = site_info["atom_index"]
            direction = np.array(site_info.get("direction", [1.0, 0.0, 0.0]))
            bond_length = site_info.get("bond_length", 1.54)

            # 获取片段或离子
            try:
                fragment = BuiltinMolecules.get(fragment_name)
            except KeyError:
                raise ValueError(f"未找到片段 '{fragment_name}'")

            # 放置片段
            site_position = new_positions[atom_idx]
            placed = self._place_fragment(fragment, site_position, direction, bond_length)

            atoms_to_remove.append(atom_idx)
            atoms_to_add_positions.extend(placed["positions"])
            atoms_to_add_symbols.extend(placed["symbols"])

        # 删除占位原子 (从大到小)
        for idx in sorted(atoms_to_remove, reverse=True):
            new_positions = np.delete(new_positions, idx, axis=0)
            new_symbols.pop(idx)

        # 添加片段原子
        if atoms_to_add_positions:
            new_positions = np.vstack([new_positions, np.array(atoms_to_add_positions)])
            new_symbols.extend(atoms_to_add_symbols)

        # 清理 substitution_sites (已被替换)
        new_properties.pop("substitution_sites", None)

        return Structure(
            positions=new_positions,
            symbols=new_symbols,
            cell=template.cell,
            pbc=template.pbc,
            properties=new_properties,
            name=template.name,
        )

    def _place_fragment(
        self,
        fragment: Structure,
        site_position: np.ndarray,
        direction: np.ndarray,
        bond_length: float,
    ) -> Dict[str, Any]:
        """
        将片段放置到指定位置

        Args:
            fragment: 片段 Structure
            site_position: 母体上替换位点的坐标
            direction: 从母体指向片段的方向向量 (归一化)
            bond_length: 键长

        Returns:
            {"positions": [[x,y,z], ...], "symbols": ["C", "H", ...]}
        """
        direction = np.array(direction, dtype=float)
        norm = np.linalg.norm(direction)
        if norm > 0:
            direction = direction / norm

        frag_positions = fragment.positions.copy()

        # 片段连接原子
        conn_atom = fragment.properties.get("connection_atom", 0)
        conn_pos = frag_positions[conn_atom].copy()

        # 平移：连接原子放在 site_position + direction * bond_length
        target = site_position + direction * bond_length
        offset = target - conn_pos
        frag_positions += offset

        return {
            "positions": frag_positions.tolist(),
            "symbols": list(fragment.symbols),
        }

    @staticmethod
    def count_combinations(substitutions: Dict[str, List[str]]) -> int:
        """计算组合总数"""
        total = 1
        for fragments in substitutions.values():
            total *= len(fragments)
        return total
