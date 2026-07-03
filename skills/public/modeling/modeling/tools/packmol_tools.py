"""
Packmol工具封装

封装Packmol的调用
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Optional
import subprocess
import tempfile
import shutil

from modeling.core.structure import Structure
from modeling.builders.filler import FillRequest


class PackmolTools:
    """
    Packmol工具封装

    提供Packmol的调用接口
    """

    _packmol_available: Optional[bool] = None
    _packmol_path: Optional[str] = None

    @classmethod
    def is_available(cls) -> bool:
        """检查Packmol是否可用"""
        if cls._packmol_available is None:
            # 优先用 Python 包提供的真实二进制（Windows wrapper 不转发 stdin）
            try:
                from packmol.cli import get_binary_path
                p = get_binary_path()
                if p.exists():
                    cls._packmol_path = str(p)
            except Exception:
                pass

            if cls._packmol_path is None:
                cls._packmol_path = shutil.which("packmol")

            # 如果 PATH 中找不到，检查常见的 Python Scripts 路径 (Windows)
            if cls._packmol_path is None:
                import os
                import glob
                # Windows Python Scripts 路径模式
                patterns = [
                    os.path.expanduser("~/AppData/Local/Packages/PythonSoftwareFoundation.Python.*/LocalCache/local-packages/Python*/Scripts/packmol.exe"),
                    os.path.expanduser("~/AppData/Local/Programs/Python/Python*/Scripts/packmol.exe"),
                    os.path.expanduser("~/.local/bin/packmol"),  # Linux/Mac
                ]
                for pattern in patterns:
                    matches = glob.glob(pattern)
                    if matches:
                        cls._packmol_path = matches[0]
                        break

            cls._packmol_available = cls._packmol_path is not None
        return cls._packmol_available

    @classmethod
    def is_executable(cls) -> bool:
        """额外探针：实际启动一次，确认二进制能加载（非缺 DLL）。"""
        if not cls.is_available():
            return False
        try:
            r = subprocess.run([cls._packmol_path], input="", capture_output=True,
                               text=True, timeout=5)
            return r.returncode == 0 or r.stdout != "" or r.stderr != ""
        except Exception:
            return False

    @classmethod
    def require_packmol(cls):
        """确保Packmol可用"""
        if not cls.is_available():
            raise RuntimeError(
                "此功能需要Packmol。请安装并确保在PATH中可访问。"
            )

    @classmethod
    def run(
        cls,
        requests: List[FillRequest],
        output_file: str,
        tolerance: float = 2.0,
        seed: int = -1,
        maxit: int = 20,
        working_dir: Optional[str] = None
    ) -> Structure:
        """
        运行Packmol填充

        Args:
            requests: 填充请求列表
            output_file: 输出文件路径
            tolerance: 分子间最小距离 (Å)
            seed: 随机种子
            maxit: 最大迭代次数
            working_dir: 工作目录，None则使用临时目录

        Returns:
            填充后的Structure
        """
        cls.require_packmol()

        # 使用临时目录或指定目录
        if working_dir is None:
            work_path = Path(tempfile.mkdtemp(prefix="packmol_"))
            cleanup = True
        else:
            work_path = Path(working_dir)
            work_path.mkdir(parents=True, exist_ok=True)
            cleanup = False

        try:
            # 准备分子文件
            mol_files = cls._prepare_molecule_files(requests, work_path)

            # 生成输入文件
            input_content = cls._generate_input(
                requests, mol_files, output_file,
                tolerance, seed, maxit
            )
            input_file = work_path / "packmol.inp"
            input_file.write_text(input_content)

            # Packmol 要求 `packmol < input.inp` — 某些 Windows 构建对非 tty stdin
            # 管道会 segfault，shell 重定向最稳。
            if cls._packmol_path is None:
                raise RuntimeError("Packmol binary path not resolved")

            cmd = f'"{cls._packmol_path}" < "{input_file.name}"'
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                cwd=work_path,
                timeout=600,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"Packmol failed (rc={result.returncode}). "
                    f"stdout(tail):\n{result.stdout[-1500:]}\n"
                    f"stderr(tail):\n{result.stderr[-500:]}"
                )

            # 读取输出
            from modeling.io import read_structure
            output_path = work_path / output_file
            if not output_path.exists():
                raise RuntimeError(f"Packmol未生成输出文件: {output_file}")

            return read_structure(str(output_path))

        finally:
            if cleanup:
                shutil.rmtree(work_path, ignore_errors=True)

    @classmethod
    def _prepare_molecule_files(
        cls,
        requests: List[FillRequest],
        work_path: Path
    ) -> List[str]:
        """准备分子文件"""
        from modeling.io import write_structure

        mol_files = []
        for i, req in enumerate(requests):
            filename = f"mol_{i}.pdb"
            filepath = work_path / filename
            write_structure(req.molecule, str(filepath), format='pdb')
            mol_files.append(filename)

        return mol_files

    @classmethod
    def _generate_input(
        cls,
        requests: List[FillRequest],
        mol_files: List[str],
        output_file: str,
        tolerance: float,
        seed: int,
        maxit: int
    ) -> str:
        """生成Packmol输入"""
        lines = [
            f"tolerance {tolerance}",
            f"filetype pdb",
            f"output {output_file}",
        ]

        if seed > 0:
            lines.append(f"seed {seed}")
        lines.append(f"maxit {maxit}")
        lines.append("")

        for req, mol_file in zip(requests, mol_files):
            lines.append(f"structure {mol_file}")

            if req.count is not None:
                lines.append(f"  number {req.count}")

            for region in req.regions:
                lines.append(f"  {region.to_packmol_constraint()}")

            lines.append("end structure")
            lines.append("")

        return "\n".join(lines)
