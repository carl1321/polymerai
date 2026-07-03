"""
SN2TSBuilder - SN2 过渡态结构构建器

基于三角双锥几何构型，使用经验 TS 键长生成高质量的 SN2 过渡态初始结构。
生成的结构可直接用于 Gaussian opt=(ts,calcfc) 计算。

几何特征:
  - z 轴: Nu⁻---C---LG (轴向, 近似直线 180°)
  - xy 平面: H, H, R (赤道位, 间隔 120°)
  - 中心碳呈三角双锥构型

对称性处理:
  - 当 Nu == LG 时, 强制两侧 C-X 距离完全相等
"""

from __future__ import annotations
from typing import Dict, List, Any, Tuple, Optional
import itertools
import numpy as np

from modeling.builders.base import BaseBuilder
from modeling.core.structure import Structure


class SN2TSBuilder(BaseBuilder):
    """
    SN2 过渡态构建器

    用法:
        builder = SN2TSBuilder()

        # 单个结构
        ts = builder.build(r_group="CH3", nucleophile="Br", leaving_group="Br")

        # 批量生成 (穷尽组合)
        structures = builder.build_all(
            r_groups=["F", "CH3", "NO2"],
            nucleophiles=["F", "Cl", "Br", "OH", "OOH"],
            leaving_groups=["F", "Cl", "Br", "OH", "OOH"],
        )
    """

    name = "sn2_ts"
    required_params = ["r_group", "nucleophile", "leaving_group"]
    default_params = {
        "gaussian_route": "# MP2/aug-cc-pVDZ opt=(ts,calcfc,noeigentest) freq",
        "charge": -1,
        "multiplicity": 1,
        "link0": {"nproc": "16", "mem": "16GB"},
    }

    # ========== 经验 TS 键长数据库 (Å) ==========
    # 从高质量参考结构提取, 代表 SN2 TS 中 C-X 轴向距离

    TS_BOND_LENGTHS: Dict[str, float] = {
        "F":   1.94,
        "Cl":  2.33,
        "Br":  2.54,
        "OH":  1.98,
        "OOH": 1.98,
    }

    # 赤道位 R 基团 C-R 键长
    R_BOND_LENGTHS: Dict[str, float] = {
        "F":   1.35,
        "CH3": 1.52,
        "NO2": 1.49,
    }

    # R 基团 → BuiltinMolecules 名称映射
    R_TO_FRAGMENT: Dict[str, str] = {
        "F":   "f_fragment",
        "CH3": "ch3",
        "NO2": "no2",
    }

    # Nu/LG 物种 → BuiltinMolecules 离子名称映射
    SPECIES_TO_ION: Dict[str, str] = {
        "F":   "f-",
        "Cl":  "cl-",
        "Br":  "br-",
        "OH":  "oh-",
        "OOH": "ooh-",
    }

    # 赤道位固定参数
    _CH = 1.09  # C-H 键长
    # 赤道 H 位置 (在 xy 平面, 90° 和 210°)
    _H1 = np.array([0.0, 1.09, 0.0])
    _H2 = np.array([-0.94396769, -0.545, 0.0])
    # R 基团方向 (330° = -30°)
    _R_DIR = np.array([np.cos(np.radians(330)), np.sin(np.radians(330)), 0.0])

    def build(self, **params) -> Structure:
        """
        构建单个 SN2 过渡态结构

        Args:
            r_group: R 基团名称 ("F", "CH3", "NO2")
            nucleophile: 亲核试剂 ("F", "Cl", "Br", "OH", "OOH")
            leaving_group: 离去基团 ("F", "Cl", "Br", "OH", "OOH")
            gaussian_route: Gaussian route section
            charge: 体系电荷
            multiplicity: 自旋多重度
            link0: Link0 命令字典

        Returns:
            带 Gaussian 属性的 Structure
        """
        params = self.validate_params(params)
        r_name = params["r_group"]
        nu_name = params["nucleophile"]
        lg_name = params["leaving_group"]

        # 验证物种名称
        self._validate_species(r_name, nu_name, lg_name)

        # 构建核心 (C + 2H)
        positions, symbols = self._build_core()

        # 放置 R 基团 (赤道位)
        r_pos, r_sym = self._place_r_group(r_name)
        positions = np.vstack([positions, r_pos])
        symbols.extend(r_sym)

        # 确定轴向距离 (对称性保证)
        nu_dist, lg_dist = self._resolve_ts_distance(nu_name, lg_name)

        # 放置 Nu (−z 方向)
        nu_pos, nu_sym = self._place_axial_species(nu_name, nu_dist, -1)
        positions = np.vstack([positions, nu_pos])
        symbols.extend(nu_sym)

        # 放置 LG (+z 方向)
        lg_pos, lg_sym = self._place_axial_species(lg_name, lg_dist, +1)
        positions = np.vstack([positions, lg_pos])
        symbols.extend(lg_sym)

        # 构建 Structure
        name = f"TS_{r_name}_Nu{nu_name}_LG{lg_name}"
        structure = Structure(
            positions=positions,
            symbols=symbols,
            name=name,
        )

        # 设置 Gaussian 属性
        structure = self._set_gaussian_properties(
            structure, r_name, nu_name, lg_name, params
        )

        return structure

    def build_all(
        self,
        r_groups: List[str],
        nucleophiles: List[str],
        leaving_groups: List[str],
        **kwargs,
    ) -> List[Structure]:
        """
        批量生成所有 R × Nu × LG 组合

        Args:
            r_groups: R 基团列表
            nucleophiles: 亲核试剂列表
            leaving_groups: 离去基团列表
            **kwargs: 传递给 build() 的额外参数

        Returns:
            所有组合的 Structure 列表
        """
        results = []
        for r, nu, lg in itertools.product(r_groups, nucleophiles, leaving_groups):
            structure = self.build(
                r_group=r, nucleophile=nu, leaving_group=lg, **kwargs
            )
            results.append(structure)
        return results

    @staticmethod
    def count_combinations(
        r_groups: List[str],
        nucleophiles: List[str],
        leaving_groups: List[str],
    ) -> int:
        """计算组合总数"""
        return len(r_groups) * len(nucleophiles) * len(leaving_groups)

    # ========== 内部方法 ==========

    def _validate_species(self, r_name: str, nu_name: str, lg_name: str):
        """验证所有物种名称合法"""
        if r_name not in self.R_BOND_LENGTHS:
            raise ValueError(
                f"未知 R 基团: '{r_name}'。"
                f"可选: {list(self.R_BOND_LENGTHS.keys())}"
            )
        for name, label in [(nu_name, "nucleophile"), (lg_name, "leaving_group")]:
            if name not in self.TS_BOND_LENGTHS:
                raise ValueError(
                    f"未知 {label}: '{name}'。"
                    f"可选: {list(self.TS_BOND_LENGTHS.keys())}"
                )

    def _build_core(self) -> Tuple[np.ndarray, List[str]]:
        """
        构建中心 CH₂ 单元: C 在原点, 两个 H 在赤道面

        Returns:
            (positions (3,3), symbols ['C', 'H', 'H'])
        """
        positions = np.array([
            [0.0, 0.0, 0.0],   # C (中心)
            self._H1,            # H1 (90°)
            self._H2,            # H2 (210°)
        ])
        return positions, ['C', 'H', 'H']

    def _place_r_group(self, r_name: str) -> Tuple[np.ndarray, List[str]]:
        """
        在赤道位放置 R 基团 (330° 方向)

        对多原子片段进行旋转对齐:
        1. 将片段连接方向对齐到 R 方向 (指向中心 C 的反方向)
        2. 绕 C-R 键轴设置二面角, 使片段 H 原子不与反应轴冲突

        Returns:
            (positions (N,3), symbols)
        """
        from modeling.resources.molecules import BuiltinMolecules

        bond_length = self.R_BOND_LENGTHS[r_name]
        r_dir = self._R_DIR  # 已归一化
        target_pos = r_dir * bond_length

        frag_name = self.R_TO_FRAGMENT[r_name]
        fragment = BuiltinMolecules.get(frag_name)

        if fragment.n_atoms == 1:
            # 单原子 (F)
            return np.array([target_pos]), list(fragment.symbols)

        # 多原子片段 — 需要旋转
        conn_idx = fragment.properties.get("connection_atom", 0)
        frag_pos = fragment.positions.copy()

        # 平移: 连接原子到原点
        frag_pos -= frag_pos[conn_idx]

        # 计算片段的 "连接方向" — 从连接原子指向其他原子质心的反方向
        # (即: 从连接原子指向母体的方向)
        other_mask = np.ones(len(frag_pos), dtype=bool)
        other_mask[conn_idx] = False
        other_centroid = frag_pos[other_mask].mean(axis=0)
        frag_outward = other_centroid  # 片段"伸展"方向
        frag_inward = -frag_outward    # 片段→母体方向

        if np.linalg.norm(frag_inward) < 1e-10:
            frag_inward = np.array([1.0, 0.0, 0.0])

        # 目标: 片段→母体方向 对齐到 -R_DIR (从 R 位置指回中心 C)
        target_inward = -r_dir

        from modeling.transforms.rotate import RotateTransform
        R_align = RotateTransform.align_vector_rotation(frag_inward, target_inward)

        # 应用旋转 (绕连接原子=原点)
        frag_pos = (R_align @ frag_pos.T).T

        # 对 CH3: 设置二面角, 使一个 H 大致在 xy 平面, 另两个在 z = ±0.89
        # 对 NO2: 设置二面角, 使 NO2 平面垂直于 xy 平面 (O 在 z = ±1.08)
        frag_pos = self._set_dihedral(frag_pos, conn_idx, r_name, r_dir)

        # 平移: 连接原子到目标位置
        frag_pos += target_pos

        return frag_pos, list(fragment.symbols)

    def _set_dihedral(
        self,
        positions: np.ndarray,
        conn_idx: int,
        r_name: str,
        r_dir: np.ndarray,
    ) -> np.ndarray:
        """
        绕 C-R 键轴旋转片段, 设置正确的二面角

        目标 (基于参考结构):
        - CH3: 一个 H 大致在 xy 平面 (z≈0), 另两个在 z ≈ ±0.89
        - NO2: 两个 O 在 z ≈ ±1.08 (NO2 平面垂直于赤道面)
        """
        from modeling.transforms.rotate import RotateTransform

        other_mask = np.ones(len(positions), dtype=bool)
        other_mask[conn_idx] = False
        other_pos = positions[other_mask]

        if r_name == "CH3":
            # 找到当前 H 中 z 分量最大的那个
            # 目标: 这个 H 的 z 应该接近 0 (在 xy 平面)
            # 选 z 绝对值最大的 H, 将其旋转到 z≈0
            z_vals = other_pos[:, 2]
            max_z_idx = np.argmax(np.abs(z_vals))
            current_z = z_vals[max_z_idx]

            if abs(current_z) > 0.01:
                # 需要绕 R 方向旋转使这个 H 的 z → 0
                h_pos = other_pos[max_z_idx]
                # 投影到垂直于 r_dir 的平面
                h_perp = h_pos - np.dot(h_pos, r_dir) * r_dir
                h_perp_norm = np.linalg.norm(h_perp)
                if h_perp_norm > 0.01:
                    # 当前方位角
                    # 要让 z 分量为 0, 需要旋转到 xy 平面
                    # 目标: h_perp 应该没有 z 分量
                    # 计算需要的旋转角
                    current_angle = np.arctan2(h_perp[2], h_perp[1])
                    # 目标角: h_perp 在 y 方向 (z=0)
                    # 但需要考虑方向 — 让 y 分量为正
                    target_angle = 0.0  # h_perp 在 y>0, z=0
                    dihedral_rot = target_angle - current_angle
                    R_dih = RotateTransform._rotation_matrix(r_dir, dihedral_rot)
                    positions = (R_dih @ positions.T).T

        elif r_name == "NO2":
            # NO2: 两个 O 应该在 z = ±值 (NO2 平面垂直于 xy)
            # 当前 O 的 z 分量
            o_pos = other_pos  # 两个 O
            z_vals = o_pos[:, 2]

            if abs(z_vals[0] - z_vals[1]) < 0.01:
                # 两个 O 的 z 相同 → NO2 平面在 xy 平面中
                # 需要旋转 90° 使 NO2 平面垂直于 xy
                R_dih = RotateTransform._rotation_matrix(r_dir, np.pi / 2)
                positions = (R_dih @ positions.T).T
            elif abs(z_vals[0] + z_vals[1]) > 0.01:
                # z 不对称, 调整
                avg_z = (z_vals[0] + z_vals[1]) / 2
                if abs(avg_z) > 0.01:
                    # 旋转使两个 O 关于 z=0 对称
                    o_mid = o_pos.mean(axis=0)
                    o_mid_perp = o_mid - np.dot(o_mid, r_dir) * r_dir
                    current_angle = np.arctan2(o_mid_perp[2], o_mid_perp[1])
                    R_dih = RotateTransform._rotation_matrix(r_dir, -current_angle)
                    positions = (R_dih @ positions.T).T

        return positions

    def _place_axial_species(
        self,
        species_name: str,
        distance: float,
        z_sign: int,
    ) -> Tuple[np.ndarray, List[str]]:
        """
        沿 z 轴放置亲核试剂或离去基团

        Args:
            species_name: 物种名称 ("F", "Cl", "Br", "OH", "OOH")
            distance: C-X 距离
            z_sign: +1 (LG, +z) 或 -1 (Nu, -z)

        Returns:
            (positions, symbols)
        """
        from modeling.resources.molecules import BuiltinMolecules
        from modeling.transforms.rotate import RotateTransform

        ion_name = self.SPECIES_TO_ION[species_name]
        ion = BuiltinMolecules.get(ion_name)

        target_z = z_sign * distance

        if ion.n_atoms == 1:
            # 单原子 (F, Cl, Br)
            return np.array([[0.0, 0.0, target_z]]), list(ion.symbols)

        # 多原子 (OH, OOH)
        conn_idx = ion.properties.get("connection_atom", 0)
        pos = ion.positions.copy()

        # 平移: 连接原子到原点
        pos -= pos[conn_idx]

        # 离子的自然轴: 从连接原子指向其他原子质心
        other_mask = np.ones(len(pos), dtype=bool)
        other_mask[conn_idx] = False
        other_centroid = pos[other_mask].mean(axis=0)
        natural_axis = other_centroid
        if np.linalg.norm(natural_axis) < 1e-10:
            natural_axis = np.array([1.0, 0.0, 0.0])

        # 目标朝向: 离子从 C 伸出, 其余原子偏离 z 轴约 109° (sp3 角)
        # 具体: 连接原子在 z 轴, 其余原子向 +x 偏转
        # 构造目标方向: 从连接原子指向其余原子的方向
        # 应该与 C→连接原子 方向成 ~109° 角
        z_axis = np.array([0.0, 0.0, float(z_sign)])
        # 期望的"其余原子"方向: 偏离 -z_axis 约 109° (即偏离 z 轴约 71°)
        sp3_angle = np.radians(109.47)
        # 在 xz 平面构造目标方向
        target_outward = np.array([
            np.sin(np.pi - sp3_angle),  # x 分量 (正)
            0.0,                         # y 分量 (在 xz 平面)
            z_sign * np.cos(np.pi - sp3_angle),  # z 分量
        ])

        # 旋转: 将自然轴对齐到目标方向
        R_align = RotateTransform.align_vector_rotation(natural_axis, target_outward)
        pos = (R_align @ pos.T).T

        # 额外约束: 将最重的非连接原子旋转到 xz 平面 (y=0)
        # 这消除了绕 centroid 方向的自由旋转
        if ion.n_atoms >= 3:
            other_idx = np.where(other_mask)[0]
            # 选择第一个非 H 的非连接原子; 否则选第一个
            target_idx = other_idx[0]
            for j in other_idx:
                if ion.symbols[j] != 'H':
                    target_idx = j
                    break
            heavy_pos = pos[target_idx]
            # 投影到垂直于 z 轴的平面
            heavy_xy = np.array([heavy_pos[0], heavy_pos[1]])
            if np.linalg.norm(heavy_xy) > 0.01:
                # 旋转绕 z 轴使 y → 0 (即放入 xz 平面)
                angle_to_xz = -np.arctan2(heavy_xy[1], heavy_xy[0])
                # 只旋转使 y=0, 保持 x>0
                R_zrot = RotateTransform._rotation_matrix(
                    np.array([0.0, 0.0, 1.0]), angle_to_xz
                )
                pos = (R_zrot @ pos.T).T

        # 平移到目标位置
        pos += np.array([0.0, 0.0, target_z])

        return pos, list(ion.symbols)

    def _resolve_ts_distance(
        self, nu_name: str, lg_name: str
    ) -> Tuple[float, float]:
        """
        确定 Nu-C 和 C-LG 距离

        关键: 当 Nu == LG 时, 强制使用完全相同的距离 (对称性)

        Returns:
            (nu_distance, lg_distance)
        """
        nu_dist = self.TS_BOND_LENGTHS[nu_name]
        lg_dist = self.TS_BOND_LENGTHS[lg_name]

        if nu_name == lg_name:
            # 对称反应 → 强制对称
            return nu_dist, nu_dist

        return nu_dist, lg_dist

    def _set_gaussian_properties(
        self,
        structure: Structure,
        r_name: str,
        nu_name: str,
        lg_name: str,
        params: Dict[str, Any],
    ) -> Structure:
        """设置 Gaussian 输入文件所需的属性"""
        import copy

        name = structure.name
        props = copy.deepcopy(structure.properties)

        props["gaussian_route"] = params.get(
            "gaussian_route",
            "# MP2/aug-cc-pVDZ opt=(ts,calcfc,noeigentest) freq"
        )
        props["charge"] = params.get("charge", -1)
        props["multiplicity"] = params.get("multiplicity", 1)

        link0 = params.get("link0", {"nproc": "16", "mem": "16GB"})
        link0 = dict(link0)  # copy
        link0.setdefault("chk", f"{name}.chk")
        props["link0"] = link0

        props["title"] = (
            f"SN2 TS: [{nu_name}]---CH2({r_name})---[{lg_name}], "
            f"charge={props['charge']}"
        )

        return Structure(
            positions=structure.positions,
            symbols=list(structure.symbols),
            cell=structure.cell,
            pbc=structure.pbc,
            properties=props,
            name=name,
        )
