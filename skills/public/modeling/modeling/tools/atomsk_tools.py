"""
Atomsk 工具封装

原子结构操作命令行工具
"""

from __future__ import annotations
from typing import Optional, List, Union, Tuple, Dict, Any
from pathlib import Path
import subprocess
import tempfile
import shutil

from modeling.core.structure import Structure


class AtomskTools:
    """
    Atomsk 工具封装

    Atomsk 是一个强大的命令行工具，用于创建和操作原子结构

    功能:
    - 缺陷创建 (空位、间隙、替换)
    - 位错插入 (刃型、螺型、混合)
    - 晶界/多晶构建
    - 表面/超胞构建
    - 格式转换

    参考: https://atomsk.univ-lille.fr/
    """

    _atomsk_available: Optional[bool] = None
    _atomsk_path: Optional[str] = None

    @classmethod
    def is_available(cls) -> bool:
        """检查 Atomsk 是否可用"""
        if cls._atomsk_available is None:
            cls._atomsk_path = shutil.which("atomsk")

            # 如果 PATH 中找不到，检查常见安装路径
            if cls._atomsk_path is None:
                import os
                common_paths = [
                    r"C:\Program Files (x86)\Atomsk\atomsk.exe",
                    r"C:\Program Files\Atomsk\atomsk.exe",
                    os.path.expanduser("~/tools/atomsk/atomsk.exe"),
                    "/usr/local/bin/atomsk",  # Linux/Mac
                    "/usr/bin/atomsk",
                ]
                for path in common_paths:
                    if os.path.isfile(path):
                        cls._atomsk_path = path
                        break

            cls._atomsk_available = cls._atomsk_path is not None
        return cls._atomsk_available

    @classmethod
    def require_atomsk(cls):
        """确保 Atomsk 可用"""
        if not cls.is_available():
            raise RuntimeError(
                "此功能需要 Atomsk。请从 https://atomsk.univ-lille.fr/ 下载安装"
            )

    # ==================== 缺陷创建 ====================

    @classmethod
    def create_vacancy(
        cls,
        structure: Structure,
        position: Union[int, Tuple[float, float, float]],
    ) -> Structure:
        """
        创建空位缺陷

        Args:
            structure: 输入结构
            position: 空位位置
                - int: 原子索引
                - (x, y, z): 坐标位置 (Å)

        Returns:
            含空位的结构
        """
        cls.require_atomsk()

        if isinstance(position, int):
            option = f"-select {position+1} -rmatom select"
        else:
            x, y, z = position
            option = f"-rmatom {x} {y} {z}"

        return cls._run_atomsk(structure, option)

    @classmethod
    def create_interstitial(
        cls,
        structure: Structure,
        element: str,
        position: Tuple[float, float, float],
    ) -> Structure:
        """
        创建间隙原子

        Args:
            structure: 输入结构
            element: 间隙原子元素
            position: 插入位置 (x, y, z) (Å)

        Returns:
            含间隙原子的结构
        """
        cls.require_atomsk()

        x, y, z = position
        option = f"-addatom {element} at {x} {y} {z}"

        return cls._run_atomsk(structure, option)

    @classmethod
    def create_substitution(
        cls,
        structure: Structure,
        position: Union[int, Tuple[float, float, float]],
        new_element: str,
    ) -> Structure:
        """
        创建替换缺陷

        Args:
            structure: 输入结构
            position: 被替换原子位置
            new_element: 新元素

        Returns:
            含替换原子的结构
        """
        cls.require_atomsk()

        if isinstance(position, int):
            option = f"-select {position+1} -substitute select {new_element}"
        else:
            x, y, z = position
            option = f"-substitute {x} {y} {z} {new_element}"

        return cls._run_atomsk(structure, option)

    # ==================== 位错 ====================

    @classmethod
    def create_edge_dislocation(
        cls,
        structure: Structure,
        position: Tuple[float, float],
        burgers: Tuple[float, float, float],
        line_direction: str = "z",
        poisson: float = 0.3,
    ) -> Structure:
        """
        创建刃型位错

        Args:
            structure: 输入结构
            position: 位错中心 (x, y) (Å)
            burgers: Burgers 矢量 (bx, by, bz) (Å)
            line_direction: 位错线方向 ("x", "y", "z")
            poisson: 泊松比

        Returns:
            含位错的结构
        """
        cls.require_atomsk()

        px, py = position
        bx, by, bz = burgers
        option = f"-dislocation {px} {py} edge {line_direction} {bx} {by} {bz} {poisson}"

        return cls._run_atomsk(structure, option)

    @classmethod
    def create_screw_dislocation(
        cls,
        structure: Structure,
        position: Tuple[float, float],
        burgers: Tuple[float, float, float],
        line_direction: str = "z",
    ) -> Structure:
        """
        创建螺型位错

        Args:
            structure: 输入结构
            position: 位错中心 (x, y) (Å)
            burgers: Burgers 矢量 (bx, by, bz) (Å)
            line_direction: 位错线方向

        Returns:
            含位错的结构
        """
        cls.require_atomsk()

        px, py = position
        bx, by, bz = burgers
        option = f"-dislocation {px} {py} screw {line_direction} {bx} {by} {bz}"

        return cls._run_atomsk(structure, option)

    # ==================== 晶界/多晶 ====================

    @classmethod
    def create_polycrystal(
        cls,
        structure: Structure,
        box_size: Tuple[float, float, float],
        num_grains: int,
        seed: int = -1,
    ) -> Structure:
        """
        创建多晶结构 (Voronoi 方法)

        Args:
            structure: 单晶单胞
            box_size: 盒子尺寸 (lx, ly, lz) (Å)
            num_grains: 晶粒数量
            seed: 随机种子

        Returns:
            多晶结构

        TODO: 实现多晶生成
        """
        cls.require_atomsk()

        # Atomsk 多晶需要单独的参数文件
        # 这里提供占位实现
        raise NotImplementedError(
            "多晶生成需要额外的参数文件配置，请参考 Atomsk 文档"
        )

    @classmethod
    def create_grain_boundary(
        cls,
        structure: Structure,
        axis: Tuple[int, int, int],
        angle: float,
        plane: Tuple[int, int, int],
    ) -> Structure:
        """
        创建晶界

        Args:
            structure: 输入结构
            axis: 旋转轴 [u, v, w]
            angle: 旋转角度 (度)
            plane: 晶界面 (h, k, l)

        Returns:
            含晶界的双晶结构

        TODO: 实现晶界生成
        """
        cls.require_atomsk()
        raise NotImplementedError("晶界生成请参考 Atomsk 文档")

    # ==================== 结构操作 ====================

    @classmethod
    def create_supercell(
        cls,
        structure: Structure,
        nx: int,
        ny: int,
        nz: int,
    ) -> Structure:
        """
        创建超胞

        Args:
            structure: 输入结构
            nx, ny, nz: 各方向重复次数

        Returns:
            超胞结构
        """
        cls.require_atomsk()
        option = f"-duplicate {nx} {ny} {nz}"
        return cls._run_atomsk(structure, option)

    @classmethod
    def create_surface(
        cls,
        structure: Structure,
        miller: Tuple[int, int, int],
    ) -> Structure:
        """
        创建表面 (切割晶体)

        Args:
            structure: 输入晶体
            miller: Miller 指数 (h, k, l)

        Returns:
            表面结构
        """
        cls.require_atomsk()
        h, k, l = miller
        option = f"-orient [{h} {k} {l}] [0 0 1] [1 0 0]"
        return cls._run_atomsk(structure, option)

    # ==================== 分析 ====================

    @classmethod
    def compute_nye_tensor(
        cls,
        structure: Structure,
        reference: Optional[Structure] = None,
    ) -> Dict[str, Any]:
        """
        计算 Nye 张量 (位错分析)

        Args:
            structure: 含位错的结构
            reference: 参考结构 (无位错)

        Returns:
            Nye 张量分析结果

        TODO: 实现 Nye 张量计算
        """
        cls.require_atomsk()
        raise NotImplementedError("Nye 张量计算请参考 Atomsk 文档")

    # ==================== 格式转换 ====================

    @classmethod
    def convert(
        cls,
        input_file: str,
        output_file: str,
        options: Optional[List[str]] = None,
    ):
        """
        格式转换

        Args:
            input_file: 输入文件路径
            output_file: 输出文件路径
            options: 额外选项
        """
        cls.require_atomsk()

        cmd = [cls._atomsk_path, input_file, output_file]
        if options:
            cmd.extend(options)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Atomsk 转换失败:\n{result.stderr}")

    # ==================== 内部方法 ====================

    @classmethod
    def _run_atomsk(
        cls,
        structure: Structure,
        options: str,
    ) -> Structure:
        """
        运行 Atomsk 命令

        Args:
            structure: 输入结构
            options: Atomsk 选项字符串

        Returns:
            处理后的结构
        """
        # 创建临时目录
        work_dir = Path(tempfile.mkdtemp(prefix="atomsk_"))

        try:
            # 写入输入文件
            input_file = work_dir / "input.xyz"
            output_file = work_dir / "output.xyz"

            from modeling.io import write_structure, read_structure
            write_structure(structure, str(input_file))

            # 构建命令
            cmd = f"{cls._atomsk_path} {input_file} {options} {output_file}"

            # 执行
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                cwd=work_dir,
                timeout=300,
            )

            if result.returncode != 0:
                raise RuntimeError(f"Atomsk 执行失败:\n{result.stderr}")

            # 读取输出
            if not output_file.exists():
                raise RuntimeError("Atomsk 未生成输出文件")

            return read_structure(str(output_file))

        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    @classmethod
    def run_raw(
        cls,
        args: List[str],
        working_dir: Optional[str] = None,
    ) -> subprocess.CompletedProcess:
        """
        运行原始 Atomsk 命令

        Args:
            args: 命令行参数列表
            working_dir: 工作目录

        Returns:
            subprocess.CompletedProcess
        """
        cls.require_atomsk()

        cmd = [cls._atomsk_path] + args

        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=working_dir,
            timeout=600,
        )
