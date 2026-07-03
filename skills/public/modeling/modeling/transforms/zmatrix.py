"""
ZMatrixTransform - Z-matrix (内坐标) 变换

封装 chemcoord 库实现笛卡尔坐标 <-> Z-matrix 转换。
安装: pip install chemcoord
"""

from __future__ import annotations
from typing import Optional, Dict, Any, TYPE_CHECKING
from pathlib import Path
import numpy as np

from modeling.transforms.base import BaseTransform

if TYPE_CHECKING:
    from modeling.core.structure import Structure


class ZMatrixTransform(BaseTransform):
    """
    Z-matrix (内坐标) 变换器

    支持功能:
    - 笛卡尔坐标 → Z-matrix
    - Z-matrix → 笛卡尔坐标
    - 输出 Gaussian Z-matrix 格式

    参数:
        mode: "to_zmat" (默认) 或 "to_cartesian"
    """

    name = "zmatrix"
    required_params = []
    default_params = {
        "mode": "to_zmat",
    }

    _chemcoord_available: Optional[bool] = None

    @classmethod
    def is_available(cls) -> bool:
        """检查 chemcoord 是否可用"""
        if cls._chemcoord_available is None:
            try:
                import chemcoord
                cls._chemcoord_available = True
            except ImportError:
                cls._chemcoord_available = False
        return cls._chemcoord_available

    @classmethod
    def require_chemcoord(cls):
        """确保 chemcoord 可用"""
        if not cls.is_available():
            raise ImportError(
                "chemcoord 未安装。请运行: pip install chemcoord"
            )

    def apply(self, structure: "Structure") -> "Structure":
        """应用 Z-matrix 变换"""
        mode = self.params.get("mode", "to_zmat")
        if mode == "to_zmat":
            return self.cartesian_to_zmat(structure)
        elif mode == "to_cartesian":
            return self.zmat_to_cartesian(structure)
        else:
            raise ValueError(f"未知模式: {mode}。可选: to_zmat, to_cartesian")

    @classmethod
    def cartesian_to_zmat(cls, structure: "Structure") -> "Structure":
        """
        笛卡尔坐标转 Z-matrix

        结果存储在 structure.properties["zmatrix"] 中。

        Returns:
            带 Z-matrix 信息的 Structure (坐标不变)
        """
        cls.require_chemcoord()
        import chemcoord as cc
        import pandas as pd

        # 构建 chemcoord Cartesian 对象
        cart = cc.Cartesian(pd.DataFrame({
            'atom': structure.symbols,
            'x': structure.positions[:, 0],
            'y': structure.positions[:, 1],
            'z': structure.positions[:, 2],
        }))

        # 转换为 Z-matrix
        zmat = cart.get_zmat()

        # 提取 Z-matrix 数据 (通过 loc 获取底层 DataFrame)
        zdf = zmat.loc[:, :]
        zmat_data = {
            "atoms": zdf['atom'].tolist(),
            "bonds": [float(v) for v in zdf['bond'].tolist()],
            "angles": [float(v) for v in zdf['angle'].tolist()],
            "dihedrals": [float(v) for v in zdf['dihedral'].tolist()],
            "b_refs": [str(v) for v in zdf['b'].tolist()],
            "a_refs": [str(v) for v in zdf['a'].tolist()],
            "d_refs": [str(v) for v in zdf['d'].tolist()],
            # Store the serialized zmat file content for reliable round-trip
            "_zmat_string": zmat.to_zmat(buf=None),
        }

        # 返回带 Z-matrix 的结构
        from modeling.core.structure import Structure as Struct
        import copy
        new_props = copy.deepcopy(structure.properties)
        new_props["zmatrix"] = zmat_data

        return Struct(
            positions=structure.positions.copy(),
            symbols=list(structure.symbols),
            cell=structure.cell,
            pbc=structure.pbc,
            properties=new_props,
            name=structure.name,
        )

    @classmethod
    def zmat_to_cartesian(cls, structure: "Structure") -> "Structure":
        """
        Z-matrix 转笛卡尔坐标

        从 structure.properties["zmatrix"] 读取 Z-matrix。

        Returns:
            坐标已更新的 Structure
        """
        cls.require_chemcoord()
        import chemcoord as cc

        zmat_data = structure.properties.get("zmatrix")
        if zmat_data is None:
            raise ValueError("Structure 中无 zmatrix 数据。请先运行 cartesian_to_zmat。")

        # 从存储的字符串重建 Zmat (最可靠的方式)
        zmat_str = zmat_data.get("_zmat_string")
        if zmat_str is None:
            raise ValueError("Z-matrix 数据缺少 _zmat_string 字段")

        # 写入临时文件供 read_zmat 使用
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(mode='w', suffix='.zmat', delete=False) as f:
            f.write(zmat_str)
            tmpfile = f.name

        try:
            zmat = cc.Zmat.read_zmat(tmpfile)
        finally:
            os.unlink(tmpfile)

        cart = zmat.get_cartesian()

        # 提取坐标
        cart_df = cart.loc[:, :]

        from modeling.core.structure import Structure as Struct
        import copy
        new_props = copy.deepcopy(structure.properties)

        return Struct(
            positions=cart_df[['x', 'y', 'z']].values.astype(float),
            symbols=cart_df['atom'].tolist(),
            cell=structure.cell,
            pbc=structure.pbc,
            properties=new_props,
            name=structure.name,
        )

    @classmethod
    def write_zmat_gaussian(
        cls,
        structure: "Structure",
        path: str,
        route: Optional[str] = None,
    ):
        """
        以 Z-matrix 格式写入 Gaussian 输入文件

        如果 structure 已包含 zmatrix 数据则直接使用，
        否则先进行笛卡尔→Z-matrix 转换。

        Args:
            structure: Structure 对象
            path: 输出文件路径
            route: 覆盖 route section (可选)
        """
        cls.require_chemcoord()

        # 确保有 Z-matrix 数据
        if "zmatrix" not in structure.properties:
            structure = cls.cartesian_to_zmat(structure)

        zmat_data = structure.properties["zmatrix"]
        props = structure.properties

        # Gaussian 参数
        link0 = props.get("link0", {})
        route_line = route or props.get("gaussian_route", "# HF/6-31G* opt freq")
        title = props.get("title", structure.name or "Z-matrix input")
        charge = props.get("charge", 0)
        multiplicity = props.get("multiplicity", 1)
        basis_extra = props.get("basis_extra", "")

        atoms = zmat_data["atoms"]
        bonds = zmat_data.get("bonds", [])
        angles = zmat_data.get("angles", [])
        dihedrals = zmat_data.get("dihedrals", [])
        b_refs = zmat_data.get("b_refs", [])
        a_refs = zmat_data.get("a_refs", [])
        d_refs = zmat_data.get("d_refs", [])

        filepath = Path(path)
        with open(filepath, 'w', newline='\n') as f:
            # Link0
            for key, val in link0.items():
                if key.startswith("%"):
                    f.write(f"{key}={val}\n")
                else:
                    f.write(f"%{key}={val}\n")

            # Route
            f.write(f"{route_line}\n")
            f.write("\n")

            # Title
            f.write(f"{title}\n")
            f.write("\n")

            # Charge and multiplicity
            f.write(f"{charge} {multiplicity}\n")

            # Z-matrix coordinates
            n = len(atoms)
            for i in range(n):
                line = f" {atoms[i]}"
                if i >= 1 and i < len(b_refs):
                    b_ref = b_refs[i]
                    bond = bonds[i] if i < len(bonds) else 0.0
                    # chemcoord uses 0-based, Gaussian uses 1-based
                    line += f"  {int(b_ref)+1}  {bond:.6f}"
                if i >= 2 and i < len(a_refs):
                    a_ref = a_refs[i]
                    angle = angles[i] if i < len(angles) else 0.0
                    line += f"  {int(a_ref)+1}  {angle:.4f}"
                if i >= 3 and i < len(d_refs):
                    d_ref = d_refs[i]
                    dihedral = dihedrals[i] if i < len(dihedrals) else 0.0
                    line += f"  {int(d_ref)+1}  {dihedral:.4f}"
                f.write(line + "\n")

            f.write("\n")

            if basis_extra:
                f.write(f"{basis_extra}\n")
                f.write("\n")

            f.write("\n")
