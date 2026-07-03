"""
VASPKIT 工具封装

VASP 预处理/后处理工具，用于结构建模
"""

from __future__ import annotations
from typing import Optional, List, Tuple, Dict, Any, Union
from pathlib import Path
import subprocess
import tempfile
import shutil

from modeling.core.structure import Structure


class VaspkitTools:
    """
    VASPKIT 工具封装

    VASPKIT 是 VASP 的预处理/后处理工具，提供结构建模功能

    主要封装功能:
    - 异质结构建 (Task 804) - 自动晶格匹配
    - 随机替换合金 (Task 802)
    - 表面构建 (Task 803)
    - 超胞构建 (Task 401)
    - 正交超胞 (Task 800)

    参考: https://vaspkit.com/

    注意:
    - VASPKIT 是 Fortran 程序，通过命令行调用
    - 部分高级功能 (纳米管/Moiré) 需要 Pro 版本
    """

    _vaspkit_available: Optional[bool] = None
    _vaspkit_path: Optional[str] = None

    @classmethod
    def is_available(cls) -> bool:
        """检查 VASPKIT 是否可用"""
        if cls._vaspkit_available is None:
            cls._vaspkit_path = shutil.which("vaspkit")
            cls._vaspkit_available = cls._vaspkit_path is not None
        return cls._vaspkit_available

    @classmethod
    def require_vaspkit(cls):
        """确保 VASPKIT 可用"""
        if not cls.is_available():
            raise RuntimeError(
                "此功能需要 VASPKIT。请从 https://vaspkit.com/ 下载安装"
            )

    # ==================== 异质结构建 (Task 804) ====================

    @classmethod
    def build_heterostructure(
        cls,
        structure1: Structure,
        structure2: Structure,
        mismatch_tolerance: float = 0.05,
        interlayer_distance: float = 3.0,
        vacuum_thickness: float = 15.0,
        max_atoms: int = 500,
        min_angle: float = 60.0,
        max_angle: float = 120.0,
    ) -> List[Structure]:
        """
        构建异质结构

        自动寻找两个结构的晶格匹配方案并构建异质结

        Args:
            structure1: 第一层结构 (底层)
            structure2: 第二层结构 (顶层)
            mismatch_tolerance: 晶格失配容差 (0.05 = 5%)
            interlayer_distance: 层间距 (Å)
            vacuum_thickness: 真空层厚度 (Å)
            max_atoms: 最大原子数限制
            min_angle: 最小晶格角度 (度)
            max_angle: 最大晶格角度 (度)

        Returns:
            匹配的异质结构列表

        Example:
            >>> graphene = read_structure("graphene.vasp")
            >>> mos2 = read_structure("MoS2.vasp")
            >>> heteros = VaspkitTools.build_heterostructure(
            ...     graphene, mos2,
            ...     mismatch_tolerance=0.03,
            ...     interlayer_distance=3.5
            ... )
        """
        cls.require_vaspkit()

        work_dir = Path(tempfile.mkdtemp(prefix="vaspkit_hetero_"))

        try:
            from modeling.io import write_structure, read_structure

            # 写入两个 POSCAR 文件
            poscar1 = work_dir / "POSCAR1"
            poscar2 = work_dir / "POSCAR2"
            write_structure(structure1, str(poscar1), format='poscar')
            write_structure(structure2, str(poscar2), format='poscar')

            # 创建配置文件
            vaspkit_config = work_dir / ".vaspkit"
            vaspkit_config.write_text(
                f"MAX_ATOM_NUMBER = {max_atoms}\n"
                f"MIN_LATTICE_ANGLE = {min_angle}\n"
                f"MAX_LATTICE_ANGLE = {max_angle}\n"
            )

            # 准备输入参数
            # Task 804 交互输入: POSCAR1路径, POSCAR2路径, 失配容差, 层间距, 真空厚度
            input_text = (
                f"804\n"
                f"{poscar1}\n"
                f"{poscar2}\n"
                f"{mismatch_tolerance}\n"
                f"{interlayer_distance}\n"
                f"{vacuum_thickness}\n"
            )

            # 运行 VASPKIT
            result = subprocess.run(
                [cls._vaspkit_path],
                input=input_text,
                capture_output=True,
                text=True,
                cwd=work_dir,
                timeout=300,
                env={**dict(__import__('os').environ), 'HOME': str(work_dir)},
            )

            # 查找生成的异质结文件
            hetero_files = list(work_dir.glob("HETERO_*.vasp"))

            if not hetero_files:
                # 尝试其他可能的输出文件名
                hetero_files = list(work_dir.glob("*.vasp"))
                hetero_files = [f for f in hetero_files if f.name not in ["POSCAR1", "POSCAR2"]]

            structures = []
            for f in sorted(hetero_files):
                try:
                    s = read_structure(str(f))
                    s.name = f.stem
                    structures.append(s)
                except Exception:
                    continue

            return structures

        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    # ==================== 随机替换合金 (Task 802) ====================

    @classmethod
    def build_random_alloy(
        cls,
        structure: Structure,
        substitutions: Dict[str, Dict[str, int]],
        num_configurations: int = 1,
        seed: Optional[int] = None,
    ) -> List[Structure]:
        """
        生成随机替换合金

        Args:
            structure: 输入结构
            substitutions: 替换规则 {被替换元素: {新元素: 数量}}
                例: {"Fe": {"Ni": 4, "Cr": 2}} 表示将4个Fe替换为Ni，2个Fe替换为Cr
            num_configurations: 生成的构型数量
            seed: 随机种子

        Returns:
            随机合金结构列表

        Example:
            >>> bcc_fe = read_structure("Fe_bcc.vasp")
            >>> alloys = VaspkitTools.build_random_alloy(
            ...     bcc_fe,
            ...     substitutions={"Fe": {"Ni": 4, "Cr": 2}},
            ...     num_configurations=5
            ... )
        """
        cls.require_vaspkit()

        work_dir = Path(tempfile.mkdtemp(prefix="vaspkit_alloy_"))

        try:
            from modeling.io import write_structure, read_structure

            # 写入 POSCAR
            poscar = work_dir / "POSCAR"
            write_structure(structure, str(poscar), format='poscar')

            # 构建替换输入字符串
            # Task 802 格式: 被替换元素 新元素1 数量1 新元素2 数量2 ...
            sub_lines = []
            for orig_elem, replacements in substitutions.items():
                parts = [orig_elem]
                for new_elem, count in replacements.items():
                    parts.extend([new_elem, str(count)])
                sub_lines.append(" ".join(parts))

            input_text = (
                f"802\n"
                f"{len(sub_lines)}\n"  # 替换规则数量
                + "\n".join(sub_lines) + "\n"
                f"{num_configurations}\n"
            )

            if seed is not None:
                input_text += f"{seed}\n"

            # 运行 VASPKIT
            result = subprocess.run(
                [cls._vaspkit_path],
                input=input_text,
                capture_output=True,
                text=True,
                cwd=work_dir,
                timeout=300,
            )

            # 查找生成的合金文件
            alloy_files = list(work_dir.glob("ALLOY_*.vasp"))
            if not alloy_files:
                alloy_files = list(work_dir.glob("POSCAR_*"))

            structures = []
            for f in sorted(alloy_files):
                try:
                    s = read_structure(str(f))
                    s.name = f.stem
                    structures.append(s)
                except Exception:
                    continue

            return structures

        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    # ==================== 表面构建 (Task 803) ====================

    @classmethod
    def build_surface(
        cls,
        structure: Structure,
        miller_index: Tuple[int, int, int],
        layers: int = 4,
        vacuum: float = 15.0,
        symmetric: bool = True,
    ) -> Structure:
        """
        构建表面结构

        Args:
            structure: 体相结构
            miller_index: Miller 指数 (h, k, l)
            layers: 原子层数
            vacuum: 真空层厚度 (Å)
            symmetric: 是否对称 slab

        Returns:
            表面结构

        Example:
            >>> bulk_pt = read_structure("Pt_bulk.vasp")
            >>> pt_111 = VaspkitTools.build_surface(
            ...     bulk_pt,
            ...     miller_index=(1, 1, 1),
            ...     layers=5,
            ...     vacuum=15.0
            ... )
        """
        cls.require_vaspkit()

        work_dir = Path(tempfile.mkdtemp(prefix="vaspkit_surface_"))

        try:
            from modeling.io import write_structure, read_structure

            # 写入 POSCAR
            poscar = work_dir / "POSCAR"
            write_structure(structure, str(poscar), format='poscar')

            h, k, l = miller_index
            sym_flag = 1 if symmetric else 0

            input_text = (
                f"803\n"
                f"{h} {k} {l}\n"
                f"{layers}\n"
                f"{vacuum}\n"
                f"{sym_flag}\n"
            )

            # 运行 VASPKIT
            result = subprocess.run(
                [cls._vaspkit_path],
                input=input_text,
                capture_output=True,
                text=True,
                cwd=work_dir,
                timeout=300,
            )

            # 查找输出文件
            output_files = ["SURFACE.vasp", "POSCAR_SLAB", "SLAB.vasp"]
            for fname in output_files:
                output_file = work_dir / fname
                if output_file.exists():
                    s = read_structure(str(output_file))
                    s.name = f"{structure.name}_{''.join(map(str, miller_index))}"
                    return s

            raise RuntimeError("VASPKIT 未生成表面结构文件")

        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    # ==================== 超胞构建 (Task 401) ====================

    @classmethod
    def build_supercell(
        cls,
        structure: Structure,
        matrix: Union[Tuple[int, int, int], List[List[int]]],
    ) -> Structure:
        """
        构建超胞

        Args:
            structure: 输入结构
            matrix: 变换矩阵
                - (nx, ny, nz): 对角矩阵
                - 3x3 列表: 一般变换矩阵

        Returns:
            超胞结构

        Note:
            对于简单超胞，建议使用 ASE，性能更好
        """
        cls.require_vaspkit()

        work_dir = Path(tempfile.mkdtemp(prefix="vaspkit_supercell_"))

        try:
            from modeling.io import write_structure, read_structure

            # 写入 POSCAR
            poscar = work_dir / "POSCAR"
            write_structure(structure, str(poscar), format='poscar')

            # 准备变换矩阵输入
            if isinstance(matrix, (list, tuple)) and len(matrix) == 3:
                if isinstance(matrix[0], (int, float)):
                    # 对角矩阵
                    matrix_str = f"{matrix[0]} 0 0\n0 {matrix[1]} 0\n0 0 {matrix[2]}"
                else:
                    # 3x3 矩阵
                    matrix_str = "\n".join(
                        " ".join(map(str, row)) for row in matrix
                    )
            else:
                raise ValueError("matrix 必须是 (nx, ny, nz) 或 3x3 列表")

            # 写入 TRANSMAT.in
            transmat_file = work_dir / "TRANSMAT.in"
            transmat_file.write_text(matrix_str)

            input_text = "401\n"

            # 运行 VASPKIT
            result = subprocess.run(
                [cls._vaspkit_path],
                input=input_text,
                capture_output=True,
                text=True,
                cwd=work_dir,
                timeout=300,
            )

            # 查找输出文件
            output_file = work_dir / "SUPERCELL.vasp"
            if not output_file.exists():
                output_file = work_dir / "POSCAR_SUPER"

            if output_file.exists():
                s = read_structure(str(output_file))
                s.name = f"{structure.name}_supercell"
                return s

            raise RuntimeError("VASPKIT 未生成超胞文件")

        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    # ==================== 正交超胞 (Task 800) ====================

    @classmethod
    def find_orthogonal_supercell(
        cls,
        structure: Structure,
        max_atoms: int = 200,
    ) -> List[Structure]:
        """
        寻找正交超胞

        Args:
            structure: 输入结构
            max_atoms: 最大原子数限制

        Returns:
            正交超胞列表
        """
        cls.require_vaspkit()

        work_dir = Path(tempfile.mkdtemp(prefix="vaspkit_ortho_"))

        try:
            from modeling.io import write_structure, read_structure

            # 写入 POSCAR
            poscar = work_dir / "POSCAR"
            write_structure(structure, str(poscar), format='poscar')

            input_text = f"800\n{max_atoms}\n"

            # 运行 VASPKIT
            result = subprocess.run(
                [cls._vaspkit_path],
                input=input_text,
                capture_output=True,
                text=True,
                cwd=work_dir,
                timeout=300,
            )

            # 查找输出文件
            ortho_files = list(work_dir.glob("ORTHOGONAL_*.vasp"))
            if not ortho_files:
                ortho_files = list(work_dir.glob("POSCAR_ORTHO*"))

            structures = []
            for f in sorted(ortho_files):
                try:
                    s = read_structure(str(f))
                    s.name = f.stem
                    structures.append(s)
                except Exception:
                    continue

            return structures

        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    # ==================== 固定原子 (Task 402/403) ====================

    @classmethod
    def fix_atoms_by_layers(
        cls,
        structure: Structure,
        fixed_layers: int,
        direction: str = "z",
    ) -> Structure:
        """
        按层固定原子 (设置 Selective Dynamics)

        Args:
            structure: 输入结构
            fixed_layers: 固定的层数 (从底部开始)
            direction: 层方向 ("x", "y", "z")

        Returns:
            带 Selective Dynamics 的结构
        """
        cls.require_vaspkit()

        work_dir = Path(tempfile.mkdtemp(prefix="vaspkit_fix_"))

        try:
            from modeling.io import write_structure, read_structure

            # 写入 POSCAR
            poscar = work_dir / "POSCAR"
            write_structure(structure, str(poscar), format='poscar')

            direction_map = {"x": 1, "y": 2, "z": 3}
            dir_num = direction_map.get(direction.lower(), 3)

            input_text = f"402\n{dir_num}\n{fixed_layers}\n"

            # 运行 VASPKIT
            result = subprocess.run(
                [cls._vaspkit_path],
                input=input_text,
                capture_output=True,
                text=True,
                cwd=work_dir,
                timeout=300,
            )

            # 查找输出文件
            output_file = work_dir / "POSCAR_FIX"
            if not output_file.exists():
                output_file = work_dir / "POSCAR_SD"

            if output_file.exists():
                s = read_structure(str(output_file))
                s.name = f"{structure.name}_fixed"
                return s

            raise RuntimeError("VASPKIT 未生成固定原子文件")

        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    # ==================== 工具方法 ====================

    @classmethod
    def run_task(
        cls,
        task: int,
        working_dir: str,
        input_text: str = "",
        timeout: int = 300,
    ) -> subprocess.CompletedProcess:
        """
        运行指定的 VASPKIT 任务

        Args:
            task: 任务编号
            working_dir: 工作目录 (需包含 POSCAR)
            input_text: 额外的交互输入
            timeout: 超时时间 (秒)

        Returns:
            subprocess.CompletedProcess
        """
        cls.require_vaspkit()

        full_input = f"{task}\n{input_text}"

        return subprocess.run(
            [cls._vaspkit_path],
            input=full_input,
            capture_output=True,
            text=True,
            cwd=working_dir,
            timeout=timeout,
        )

    @classmethod
    def get_version(cls) -> str:
        """获取 VASPKIT 版本"""
        cls.require_vaspkit()

        result = subprocess.run(
            [cls._vaspkit_path, "-v"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        return result.stdout.strip() or result.stderr.strip()
