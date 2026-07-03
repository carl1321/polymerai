"""
Structure - 原子结构的核心数据类

存储原子坐标、元素、盒子等信息
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import numpy as np


@dataclass
class Structure:
    """
    原子结构数据类

    Attributes:
        positions: 原子坐标 (N, 3)，单位 Å
        symbols: 元素符号列表
        cell: 晶胞/盒子参数 (3, 3) 或 (3,)，单位 Å
        pbc: 周期性边界条件 [bool, bool, bool]
        charges: 原子电荷 (可选)
        bonds: 键连接信息 (可选)

        # 扩展字段（支持不同输出格式）
        selective_dynamics: 固定原子标记 (N, 3) bool，用于 VASP
        atom_types: 力场原子类型，用于 LAMMPS
        residues: 残基归属，用于 PDB/GRO
        velocities: 初始速度 (N, 3)，用于 LAMMPS/GRO
        properties: 自定义属性字典
    """

    positions: np.ndarray
    symbols: List[str]
    cell: Optional[np.ndarray] = None
    pbc: List[bool] = field(default_factory=lambda: [False, False, False])
    charges: Optional[np.ndarray] = None
    bonds: Optional[List[tuple]] = None

    # 扩展字段
    selective_dynamics: Optional[np.ndarray] = None  # (N, 3) bool, VASP
    atom_types: Optional[List[str]] = None           # 力场类型, LAMMPS
    residues: Optional[List[str]] = None             # 残基, PDB/GRO
    velocities: Optional[np.ndarray] = None          # (N, 3), LAMMPS/GRO
    properties: Dict[str, Any] = field(default_factory=dict)

    # 元数据
    name: str = ""
    source_file: str = ""

    def __post_init__(self):
        """数据验证和类型转换"""
        self.positions = np.asarray(self.positions, dtype=np.float64)
        if self.cell is not None:
            self.cell = np.asarray(self.cell, dtype=np.float64)
        if self.charges is not None:
            self.charges = np.asarray(self.charges, dtype=np.float64)
        if self.selective_dynamics is not None:
            self.selective_dynamics = np.asarray(self.selective_dynamics, dtype=bool)
        if self.velocities is not None:
            self.velocities = np.asarray(self.velocities, dtype=np.float64)

    @property
    def n_atoms(self) -> int:
        """原子数量"""
        return len(self.symbols)

    @property
    def bbox(self) -> np.ndarray:
        """包围盒尺寸 [dx, dy, dz]"""
        if self.n_atoms == 0:
            return np.zeros(3)
        return self.positions.max(axis=0) - self.positions.min(axis=0)

    @property
    def center_of_mass(self) -> np.ndarray:
        """质心位置"""
        # TODO: 使用真实原子质量
        return self.positions.mean(axis=0)

    @property
    def formula(self) -> str:
        """化学式"""
        from collections import Counter
        counts = Counter(self.symbols)
        return "".join(f"{el}{n if n > 1 else ''}" for el, n in sorted(counts.items()))

    def translate(self, vector: np.ndarray) -> Structure:
        """平移结构"""
        new_positions = self.positions + np.asarray(vector)
        return self._copy_with(positions=new_positions)

    def center_at(self, point: np.ndarray) -> Structure:
        """将质心移动到指定点"""
        shift = np.asarray(point) - self.center_of_mass
        return self.translate(shift)

    def _copy_with(self, **kwargs) -> Structure:
        """创建修改后的副本"""
        data = {
            "positions": self.positions.copy(),
            "symbols": self.symbols.copy(),
            "cell": self.cell.copy() if self.cell is not None else None,
            "pbc": self.pbc.copy(),
            "charges": self.charges.copy() if self.charges is not None else None,
            "bonds": self.bonds.copy() if self.bonds is not None else None,
            "selective_dynamics": self.selective_dynamics.copy() if self.selective_dynamics is not None else None,
            "atom_types": self.atom_types.copy() if self.atom_types is not None else None,
            "residues": self.residues.copy() if self.residues is not None else None,
            "velocities": self.velocities.copy() if self.velocities is not None else None,
            "properties": self.properties.copy(),
            "name": self.name,
            "source_file": self.source_file,
        }
        data.update(kwargs)
        return Structure(**data)

    @classmethod
    def empty(cls) -> Structure:
        """创建空结构"""
        return cls(positions=np.zeros((0, 3)), symbols=[])

    def __add__(self, other: Structure) -> Structure:
        """合并两个结构"""
        return merge_structures([self, other])

    def __len__(self) -> int:
        return self.n_atoms

    def __repr__(self) -> str:
        return f"Structure({self.formula}, n_atoms={self.n_atoms})"


def merge_structures(structures: List[Structure], name: str = "") -> Structure:
    """
    合并多个结构

    Args:
        structures: 结构列表
        name: 合并后的名称

    Returns:
        合并后的结构
    """
    if not structures:
        return Structure.empty()

    all_positions = []
    all_symbols = []
    all_charges = []
    has_charges = all(s.charges is not None for s in structures)

    for s in structures:
        all_positions.append(s.positions)
        all_symbols.extend(s.symbols)
        if has_charges:
            all_charges.append(s.charges)

    return Structure(
        positions=np.vstack(all_positions) if all_positions else np.zeros((0, 3)),
        symbols=all_symbols,
        cell=structures[0].cell,  # 使用第一个结构的盒子
        pbc=structures[0].pbc,
        charges=np.concatenate(all_charges) if has_charges else None,
        name=name,
    )
