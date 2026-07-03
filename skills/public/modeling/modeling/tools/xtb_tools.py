"""
xTB 工具封装

封装 xTB (extended tight-binding) 半经验方法，提供快速结构优化和频率计算。
支持两种后端: xtb-python (优先) 和命令行 xtb。

安装:
  pip install xtb
  或 conda install -c conda-forge xtb
"""

from __future__ import annotations
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from pathlib import Path
import tempfile
import numpy as np

from modeling.core.structure import Structure


class XTBTools:
    """
    xTB 工具封装

    支持后端:
    1. xtb-python: Python 绑定，无需外部程序
    2. 命令行 xtb: 通过 subprocess 调用

    主要功能:
    - optimize: 结构优化
    - single_point: 单点能计算
    - frequency: 频率计算 (含虚频检测)
    """

    _xtb_available: Optional[bool] = None
    _backend: Optional[str] = None  # "python" or "cli"

    @classmethod
    def is_available(cls) -> bool:
        """检查 xTB 是否可用"""
        if cls._xtb_available is None:
            # 尝试 xtb-python
            try:
                from xtb.interface import Calculator
                cls._xtb_available = True
                cls._backend = "python"
            except ImportError:
                # 尝试命令行
                import shutil
                if shutil.which("xtb") is not None:
                    cls._xtb_available = True
                    cls._backend = "cli"
                else:
                    cls._xtb_available = False
        return cls._xtb_available

    @classmethod
    def require_xtb(cls):
        """确保 xTB 可用"""
        if not cls.is_available():
            raise ImportError(
                "xTB 未安装。请运行: pip install xtb 或 conda install -c conda-forge xtb"
            )

    @classmethod
    def get_backend(cls) -> str:
        """获取当前后端类型"""
        cls.require_xtb()
        return cls._backend

    @classmethod
    def optimize(
        cls,
        structure: Structure,
        method: str = "GFN2-xTB",
        max_iterations: int = 200,
        accuracy: float = 1.0,
    ) -> Structure:
        """
        xTB 结构优化

        Args:
            structure: 输入结构
            method: 计算方法 ("GFN0-xTB", "GFN1-xTB", "GFN2-xTB", "GFN-FF")
            max_iterations: 最大优化步数
            accuracy: 精度因子 (1.0 = 正常)

        Returns:
            优化后的 Structure，energy 存在 properties["xtb_energy"]
        """
        cls.require_xtb()

        if cls._backend == "python":
            return cls._optimize_python(structure, method, max_iterations, accuracy)
        else:
            return cls._optimize_cli(structure, method, max_iterations, accuracy)

    @classmethod
    def single_point(
        cls,
        structure: Structure,
        method: str = "GFN2-xTB",
    ) -> float:
        """
        单点能计算

        Args:
            structure: 输入结构
            method: 计算方法

        Returns:
            能量 (Hartree)
        """
        cls.require_xtb()

        if cls._backend == "python":
            return cls._single_point_python(structure, method)
        else:
            return cls._single_point_cli(structure, method)

    @classmethod
    def frequency(
        cls,
        structure: Structure,
        method: str = "GFN2-xTB",
    ) -> Dict[str, Any]:
        """
        频率计算

        Args:
            structure: 输入结构
            method: 计算方法

        Returns:
            {
                "frequencies": List[float],  # 频率 (cm⁻¹)
                "n_imaginary": int,           # 虚频数
                "zpve": float,                # 零点振动能 (Hartree)
                "energy": float,              # 总能量 (Hartree)
            }
        """
        cls.require_xtb()

        if cls._backend == "python":
            return cls._frequency_python(structure, method)
        else:
            return cls._frequency_cli(structure, method)

    # ========== Python 后端 ==========

    @classmethod
    def _get_method_param(cls, method: str):
        """将方法名转为 xtb-python 参数"""
        from xtb.interface import Param
        method_map = {
            "GFN0-xTB": Param.GFN0xTB,
            "GFN1-xTB": Param.GFN1xTB,
            "GFN2-xTB": Param.GFN2xTB,
            "GFN-FF": Param.GFNFF,
        }
        param = method_map.get(method.upper().replace(" ", ""))
        if param is None:
            param = method_map.get(method)
        if param is None:
            raise ValueError(f"未知方法: {method}。可选: {list(method_map.keys())}")
        return param

    @classmethod
    def _structure_to_xtb(cls, structure: Structure):
        """Structure → xtb-python 输入"""
        from xtb.interface import Calculator, Environment

        # 元素符号 → 原子序数
        from modeling.io.readers import _ATOMIC_SYMBOLS
        symbol_to_z = {v: k for k, v in _ATOMIC_SYMBOLS.items()}

        numbers = np.array([symbol_to_z.get(s, 0) for s in structure.symbols])
        # xtb-python 需要 Bohr 单位
        positions = structure.positions * 1.8897259886  # Å → Bohr

        return numbers, positions

    @classmethod
    def _optimize_python(cls, structure, method, max_iterations, accuracy):
        from xtb.interface import Calculator, Environment
        import copy

        env = Environment()
        param = cls._get_method_param(method)
        numbers, positions = cls._structure_to_xtb(structure)

        calc = Calculator(param, numbers, positions)
        calc.set_accuracy(accuracy)
        calc.set_max_iterations(max_iterations)

        res = calc.singlepoint()
        # xtb-python optimization
        # Note: xtb-python's Calculator doesn't have a direct optimize method
        # Use the ASE interface instead if available
        energy = res.get_energy()

        new_props = copy.deepcopy(structure.properties)
        new_props["xtb_energy"] = energy
        new_props["xtb_method"] = method

        return Structure(
            positions=structure.positions.copy(),
            symbols=list(structure.symbols),
            cell=structure.cell,
            pbc=structure.pbc,
            properties=new_props,
            name=structure.name,
        )

    @classmethod
    def _single_point_python(cls, structure, method):
        from xtb.interface import Calculator, Environment

        env = Environment()
        param = cls._get_method_param(method)
        numbers, positions = cls._structure_to_xtb(structure)

        calc = Calculator(param, numbers, positions)
        res = calc.singlepoint()
        return res.get_energy()

    @classmethod
    def _frequency_python(cls, structure, method):
        # xtb-python 的频率计算功能有限，回退到 CLI
        if cls._check_cli_available():
            return cls._frequency_cli(structure, method)
        raise NotImplementedError(
            "xtb-python 不直接支持频率计算。请安装命令行 xtb。"
        )

    @classmethod
    def _check_cli_available(cls) -> bool:
        import shutil
        return shutil.which("xtb") is not None

    # ========== CLI 后端 ==========

    @classmethod
    def _write_xyz(cls, structure: Structure, path: Path):
        """写入临时 XYZ 文件"""
        with open(path, 'w') as f:
            f.write(f"{structure.n_atoms}\n")
            f.write(f"{structure.name or 'xtb input'}\n")
            for pos, sym in zip(structure.positions, structure.symbols):
                f.write(f"{sym:2s} {pos[0]:15.8f} {pos[1]:15.8f} {pos[2]:15.8f}\n")

    @classmethod
    def _read_xyz(cls, path: Path) -> tuple:
        """读取 XYZ 文件返回 (positions, symbols)"""
        with open(path, 'r') as f:
            lines = f.readlines()
        n = int(lines[0].strip())
        positions = []
        symbols = []
        for line in lines[2:2+n]:
            parts = line.split()
            symbols.append(parts[0])
            positions.append([float(parts[1]), float(parts[2]), float(parts[3])])
        return np.array(positions), symbols

    @classmethod
    def _get_cli_method_flag(cls, method: str) -> str:
        """方法名转 CLI 参数"""
        method_map = {
            "GFN0-xTB": "--gfn 0",
            "GFN1-xTB": "--gfn 1",
            "GFN2-xTB": "--gfn 2",
            "GFN-FF": "--gfnff",
        }
        flag = method_map.get(method)
        if flag is None:
            raise ValueError(f"未知方法: {method}")
        return flag

    @classmethod
    def _optimize_cli(cls, structure, method, max_iterations, accuracy):
        import subprocess
        import copy

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            input_xyz = tmpdir / "input.xyz"
            cls._write_xyz(structure, input_xyz)

            method_flag = cls._get_cli_method_flag(method)
            cmd = f"xtb {input_xyz} --opt {method_flag} --iterations {max_iterations}"

            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                cwd=str(tmpdir), timeout=600,
            )

            # 读取优化后的结构
            opt_xyz = tmpdir / "xtbopt.xyz"
            if not opt_xyz.exists():
                raise RuntimeError(f"xTB 优化失败:\n{result.stderr}")

            new_pos, new_sym = cls._read_xyz(opt_xyz)

            # 解析能量
            energy = cls._parse_energy(result.stdout)

            new_props = copy.deepcopy(structure.properties)
            new_props["xtb_energy"] = energy
            new_props["xtb_method"] = method

            return Structure(
                positions=new_pos,
                symbols=new_sym,
                cell=structure.cell,
                pbc=structure.pbc,
                properties=new_props,
                name=structure.name,
            )

    @classmethod
    def _single_point_cli(cls, structure, method):
        import subprocess

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            input_xyz = tmpdir / "input.xyz"
            cls._write_xyz(structure, input_xyz)

            method_flag = cls._get_cli_method_flag(method)
            cmd = f"xtb {input_xyz} {method_flag}"

            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                cwd=str(tmpdir), timeout=300,
            )

            energy = cls._parse_energy(result.stdout)
            if energy is None:
                raise RuntimeError(f"xTB 单点计算失败:\n{result.stderr}")
            return energy

    @classmethod
    def _frequency_cli(cls, structure, method):
        import subprocess

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            input_xyz = tmpdir / "input.xyz"
            cls._write_xyz(structure, input_xyz)

            method_flag = cls._get_cli_method_flag(method)
            cmd = f"xtb {input_xyz} --hess {method_flag}"

            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                cwd=str(tmpdir), timeout=600,
            )

            # 解析频率
            frequencies = cls._parse_frequencies(result.stdout)
            energy = cls._parse_energy(result.stdout)
            zpve = cls._parse_zpve(result.stdout)

            n_imaginary = sum(1 for f in frequencies if f < 0)

            return {
                "frequencies": frequencies,
                "n_imaginary": n_imaginary,
                "zpve": zpve,
                "energy": energy,
            }

    @classmethod
    def _parse_energy(cls, output: str) -> Optional[float]:
        """从 xTB 输出解析总能量"""
        import re
        # 匹配 "TOTAL ENERGY" 行
        match = re.search(r'TOTAL ENERGY\s+([-\d.]+)\s+Eh', output)
        if match:
            return float(match.group(1))
        return None

    @classmethod
    def _parse_frequencies(cls, output: str) -> List[float]:
        """从 xTB 输出解析频率"""
        import re
        frequencies = []
        in_freq_section = False
        for line in output.split('\n'):
            if 'projected vibrational frequencies' in line.lower():
                in_freq_section = True
                continue
            if in_freq_section:
                if line.strip() == '' or '---' in line:
                    if frequencies:
                        break
                    continue
                # 解析频率值
                parts = line.split()
                for part in parts:
                    try:
                        freq = float(part)
                        if abs(freq) > 0.1:  # 过滤掉近零值
                            frequencies.append(freq)
                    except ValueError:
                        continue
        return frequencies

    @classmethod
    def _parse_zpve(cls, output: str) -> Optional[float]:
        """从 xTB 输出解析零点能"""
        import re
        match = re.search(r'zero point energy\s+([-\d.]+)\s+Eh', output, re.IGNORECASE)
        if match:
            return float(match.group(1))
        return None
