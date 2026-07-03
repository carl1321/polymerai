"""
OVITO 工具封装

原子结构可视化与分析
"""

from __future__ import annotations
from typing import Optional, List, Dict, Any, Union, Tuple
from pathlib import Path
import numpy as np

from modeling.core.structure import Structure


class OvitoTools:
    """
    OVITO 工具封装

    OVITO 是强大的原子结构可视化和分析工具

    功能:
    - 结构分析 (RDF, CNA, PTM, Voronoi)
    - 位错分析 (DXA)
    - 晶界分析
    - 可视化渲染

    参考: https://www.ovito.org/
    """

    _ovito_available: Optional[bool] = None

    @classmethod
    def is_available(cls) -> bool:
        """检查 OVITO Python 模块是否可用"""
        if cls._ovito_available is None:
            try:
                import ovito
                cls._ovito_available = True
            except ImportError:
                cls._ovito_available = False
        return cls._ovito_available

    @classmethod
    def require_ovito(cls):
        """确保 OVITO 可用"""
        if not cls.is_available():
            raise ImportError(
                "此功能需要 OVITO Python 模块。"
                "请安装: pip install ovito"
            )

    # ==================== 结构分析 ====================

    @classmethod
    def compute_rdf(
        cls,
        structure: Structure,
        cutoff: float = 10.0,
        bins: int = 100,
    ) -> Dict[str, np.ndarray]:
        """
        计算径向分布函数 (RDF)

        Args:
            structure: 输入结构
            cutoff: 截断半径 (Å)
            bins: 直方图 bin 数量

        Returns:
            {"r": 距离数组, "g_r": RDF 值}
        """
        cls.require_ovito()
        from ovito.io import import_file
        from ovito.modifiers import CoordinationAnalysisModifier

        # 转换为 OVITO 数据
        data = cls._structure_to_ovito(structure)

        # 添加 RDF 计算修饰器
        modifier = CoordinationAnalysisModifier(
            cutoff=cutoff,
            number_of_bins=bins,
        )
        data.modifiers.append(modifier)
        data.compute()

        # 提取结果
        rdf_table = data.tables['coordination-rdf']

        return {
            "r": np.array(rdf_table['Pair Separation']),
            "g_r": np.array(rdf_table['g(r)']),
        }

    @classmethod
    def identify_crystal_structure(
        cls,
        structure: Structure,
        method: str = "ptm",
    ) -> Dict[str, Any]:
        """
        识别晶体结构类型

        Args:
            structure: 输入结构
            method: 识别方法
                - "cna": Common Neighbor Analysis
                - "ptm": Polyhedral Template Matching

        Returns:
            结构类型统计
        """
        cls.require_ovito()

        data = cls._structure_to_ovito(structure)

        if method == "cna":
            from ovito.modifiers import CommonNeighborAnalysisModifier
            modifier = CommonNeighborAnalysisModifier()
        elif method == "ptm":
            from ovito.modifiers import PolyhedralTemplateMatchingModifier
            modifier = PolyhedralTemplateMatchingModifier()
        else:
            raise ValueError(f"未知方法: {method}")

        data.modifiers.append(modifier)
        data.compute()

        # 统计结构类型
        structure_types = data.particles['Structure Type']
        unique, counts = np.unique(structure_types, return_counts=True)

        return {
            "method": method,
            "structure_types": dict(zip(unique.tolist(), counts.tolist())),
            "total_atoms": len(structure_types),
        }

    @classmethod
    def analyze_dislocations(
        cls,
        structure: Structure,
        crystal_structure: str = "fcc",
    ) -> Dict[str, Any]:
        """
        位错分析 (DXA)

        Args:
            structure: 输入结构
            crystal_structure: 晶体结构类型 ("fcc", "bcc", "hcp")

        Returns:
            位错分析结果
        """
        cls.require_ovito()
        from ovito.modifiers import DislocationAnalysisModifier

        data = cls._structure_to_ovito(structure)

        # 设置晶体结构
        struct_map = {
            "fcc": DislocationAnalysisModifier.Lattice.FCC,
            "bcc": DislocationAnalysisModifier.Lattice.BCC,
            "hcp": DislocationAnalysisModifier.Lattice.HCP,
        }

        if crystal_structure.lower() not in struct_map:
            raise ValueError(f"不支持的晶体结构: {crystal_structure}")

        modifier = DislocationAnalysisModifier(
            input_crystal_structure=struct_map[crystal_structure.lower()]
        )
        data.modifiers.append(modifier)
        data.compute()

        # 提取位错信息
        dislocations = data.dislocations

        result = {
            "total_length": 0.0,
            "segments": [],
        }

        for segment in dislocations.segments:
            result["segments"].append({
                "burgers_vector": segment.true_burgers_vector.tolist(),
                "length": segment.length,
            })
            result["total_length"] += segment.length

        return result

    @classmethod
    def compute_voronoi(
        cls,
        structure: Structure,
    ) -> Dict[str, np.ndarray]:
        """
        Voronoi 分析

        Args:
            structure: 输入结构

        Returns:
            Voronoi 分析结果 (体积、面数等)
        """
        cls.require_ovito()
        from ovito.modifiers import VoronoiAnalysisModifier

        data = cls._structure_to_ovito(structure)

        modifier = VoronoiAnalysisModifier(
            compute_indices=True,
            use_radii=False,
        )
        data.modifiers.append(modifier)
        data.compute()

        return {
            "volumes": np.array(data.particles['Atomic Volume']),
            "coordination": np.array(data.particles['Coordination']),
        }

    # ==================== 可视化 ====================

    @classmethod
    def render_image(
        cls,
        structure: Structure,
        output_file: str,
        size: Tuple[int, int] = (800, 600),
        camera_dir: Tuple[float, float, float] = (1, 1, 1),
    ):
        """
        渲染结构图像

        Args:
            structure: 输入结构
            output_file: 输出图像路径
            size: 图像尺寸 (width, height)
            camera_dir: 相机方向
        """
        cls.require_ovito()
        from ovito.vis import Viewport, TachyonRenderer

        data = cls._structure_to_ovito(structure)
        data.compute()

        # 设置视口
        vp = Viewport(type=Viewport.Type.Ortho)
        vp.camera_dir = camera_dir
        vp.zoom_all(size=size)

        # 渲染
        vp.render_image(
            filename=output_file,
            size=size,
            renderer=TachyonRenderer(),
        )

    # ==================== 转换函数 ====================

    @classmethod
    def _structure_to_ovito(cls, structure: Structure):
        """将 Structure 转换为 OVITO DataCollection"""
        cls.require_ovito()
        from ovito.data import DataCollection, Particles, SimulationCell
        import ovito.data

        # 创建数据集
        data = DataCollection()

        # 添加粒子
        particles = Particles()
        particles.create_property('Position', data=structure.positions)

        # 元素类型
        type_property = particles.create_property('Particle Type')
        unique_elements = list(set(structure.symbols))
        for i, elem in enumerate(unique_elements):
            type_property.types.append(ovito.data.ParticleType(
                id=i+1, name=elem
            ))

        # 设置类型 ID
        type_ids = [unique_elements.index(s) + 1 for s in structure.symbols]
        type_property[:] = type_ids

        data.objects.append(particles)

        # 添加晶胞
        if structure.cell is not None:
            cell = SimulationCell()
            if structure.cell.ndim == 1:
                cell.matrix = np.diag(list(structure.cell) + [0])
            else:
                cell_matrix = np.zeros((3, 4))
                cell_matrix[:3, :3] = structure.cell
                cell.matrix = cell_matrix
            cell.pbc = tuple(structure.pbc)
            data.objects.append(cell)

        return data

    @classmethod
    def _ovito_to_structure(cls, data) -> Structure:
        """将 OVITO DataCollection 转换为 Structure"""
        particles = data.particles
        positions = np.array(particles['Position'])

        # 获取元素符号
        type_property = particles['Particle Type']
        symbols = []
        for type_id in type_property:
            ptype = type_property.types[type_id - 1]
            symbols.append(ptype.name)

        # 获取晶胞
        cell = None
        pbc = [False, False, False]
        if 'SimulationCell' in data.objects:
            sim_cell = data.cell
            cell = sim_cell.matrix[:3, :3]
            pbc = list(sim_cell.pbc)

        return Structure(
            positions=positions,
            symbols=symbols,
            cell=cell,
            pbc=pbc,
        )
