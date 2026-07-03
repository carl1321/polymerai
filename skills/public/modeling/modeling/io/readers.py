"""
StructureReader - 结构文件读取器
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional, Dict, Type
import numpy as np

from modeling.core.structure import Structure
from modeling.core.molecule import MoleculeInfo


class StructureReader:
    """
    结构文件读取器

    支持格式:
    - PDB (纯 Python)
    - XYZ (纯 Python)
    - Gaussian .gjf/.com (纯 Python)
    - CIF (需要 ASE)
    - POSCAR (需要 ASE)
    - LAMMPS data (需要 ASE)
    - GRO (需要 ASE)
    """

    # 格式检测映射
    FORMAT_EXTENSIONS = {
        '.pdb': 'pdb',
        '.xyz': 'xyz',
        '.cif': 'cif',
        '.poscar': 'poscar',
        '.vasp': 'poscar',
        '.data': 'lammps',
        '.lmp': 'lammps',
        '.gro': 'gro',
        '.gjf': 'gaussian',
        '.com': 'gaussian',
    }

    def read(self, filepath: str, format: Optional[str] = None) -> Structure:
        """
        读取结构文件

        Args:
            filepath: 文件路径
            format: 文件格式，None则自动检测

        Returns:
            Structure对象
        """
        path = Path(filepath)

        if format is None:
            format = self._detect_format(path)

        reader_method = getattr(self, f"_read_{format}", None)
        if reader_method is None:
            raise ValueError(f"不支持的格式: {format}")

        structure = reader_method(path)
        structure.source_file = str(path)

        return structure

    def _detect_format(self, path: Path) -> str:
        """检测文件格式"""
        ext = path.suffix.lower()

        # 特殊处理无后缀文件
        if ext == '' and path.name.upper() in ('POSCAR', 'CONTCAR'):
            return 'poscar'

        format = self.FORMAT_EXTENSIONS.get(ext)
        if format is None:
            raise ValueError(f"无法识别文件格式: {path}")

        return format

    def _read_pdb(self, path: Path) -> Structure:
        """读取PDB文件"""
        positions = []
        symbols = []

        with open(path, 'r') as f:
            for line in f:
                if line.startswith(('ATOM', 'HETATM')):
                    # PDB格式列位置固定
                    x = float(line[30:38])
                    y = float(line[38:46])
                    z = float(line[46:54])
                    positions.append([x, y, z])

                    # 元素符号在77-78列，或从原子名推断
                    element = line[76:78].strip()
                    if not element:
                        element = line[12:16].strip()[0]
                    symbols.append(element)

        return Structure(
            positions=np.array(positions) if positions else np.zeros((0, 3)),
            symbols=symbols,
            name=path.stem,
        )

    def _read_xyz(self, path: Path) -> Structure:
        """读取XYZ文件"""
        with open(path, 'r') as f:
            lines = f.readlines()

        n_atoms = int(lines[0].strip())
        # 第二行是注释

        positions = []
        symbols = []

        for line in lines[2:2+n_atoms]:
            parts = line.split()
            symbols.append(parts[0])
            positions.append([float(parts[1]), float(parts[2]), float(parts[3])])

        return Structure(
            positions=np.array(positions),
            symbols=symbols,
            name=path.stem,
        )

    def _read_gaussian(self, path: Path) -> Structure:
        """
        读取 Gaussian 输入文件 (.gjf/.com)

        解析 Link0、Route、Title、Charge/Multiplicity 和笛卡尔坐标。
        Gaussian 特有参数存储在 Structure.properties 中。
        """
        import re

        with open(path, 'r') as f:
            lines = f.readlines()

        # 解析各 section
        link0 = {}
        route_lines = []
        title = ""
        charge = 0
        multiplicity = 1
        positions = []
        symbols = []
        basis_extra_lines = []

        # 状态机：link0 -> route -> blank -> title -> blank -> charge_mult -> coords -> blank -> extra
        state = "link0"
        blank_count = 0

        for line in lines:
            stripped = line.strip()

            if state == "link0":
                if stripped.startswith("%"):
                    # Parse %key=value
                    match = re.match(r'^%(\w+)\s*=\s*(.+)$', stripped)
                    if match:
                        link0[match.group(1).lower()] = match.group(2).strip()
                    continue
                elif stripped.startswith("#") or stripped == "":
                    state = "route"
                    # fall through to route handling
                else:
                    state = "route"

            if state == "route":
                if stripped == "":
                    if route_lines:
                        state = "title"
                        continue
                    # Skip leading blanks
                    continue
                route_lines.append(stripped)
                continue

            if state == "title":
                if stripped == "":
                    state = "charge_mult"
                    continue
                title = stripped
                continue

            if state == "charge_mult":
                if stripped == "":
                    continue
                parts = stripped.split()
                if len(parts) >= 2:
                    try:
                        charge = int(parts[0])
                        multiplicity = int(parts[1])
                    except ValueError:
                        pass
                state = "coords"
                continue

            if state == "coords":
                if stripped == "":
                    state = "extra"
                    continue
                parts = stripped.split()
                if len(parts) >= 4:
                    sym = parts[0]
                    # Handle atomic number format (e.g., "6" instead of "C")
                    if sym.isdigit():
                        sym = _atomic_number_to_symbol(int(sym))
                    # Skip fragment flag if present (e.g., "C(Fragment=1)")
                    sym = re.sub(r'\(.*\)', '', sym)
                    try:
                        # Coordinates may start at index 1 or index 2 (with atomic type)
                        if len(parts) >= 5 and _is_float(parts[1]):
                            # format: Symbol x y z (or with extra column)
                            coords = [float(parts[-3]), float(parts[-2]), float(parts[-1])]
                        else:
                            coords = [float(parts[1]), float(parts[2]), float(parts[3])]
                        symbols.append(sym)
                        positions.append(coords)
                    except (ValueError, IndexError):
                        pass
                continue

            if state == "extra":
                if stripped:
                    basis_extra_lines.append(line.rstrip('\n'))

        route = " ".join(route_lines) if route_lines else ""

        properties = {
            "gaussian_route": route,
            "charge": charge,
            "multiplicity": multiplicity,
            "title": title,
            "link0": link0,
        }
        if basis_extra_lines:
            properties["basis_extra"] = "\n".join(basis_extra_lines)

        return Structure(
            positions=np.array(positions) if positions else np.zeros((0, 3)),
            symbols=symbols,
            name=title or path.stem,
            properties=properties,
        )

    def _read_cif(self, path: Path) -> Structure:
        """
        读取 CIF 文件

        使用 ASE 读取
        """
        from modeling.tools.ase_tools import ASETools
        return ASETools.read_file(str(path), format='cif')

    def _read_poscar(self, path: Path) -> Structure:
        """
        读取 POSCAR/VASP 文件

        使用 ASE 读取
        """
        from modeling.tools.ase_tools import ASETools
        return ASETools.read_file(str(path), format='vasp')

    def _read_lammps(self, path: Path) -> Structure:
        """
        读取 LAMMPS data 文件

        使用 ASE 读取
        """
        from modeling.tools.ase_tools import ASETools
        return ASETools.read_file(str(path), format='lammps-data')

    def _read_gro(self, path: Path) -> Structure:
        """
        读取 GROMACS GRO 文件

        使用 ASE 读取
        """
        from modeling.tools.ase_tools import ASETools
        return ASETools.read_file(str(path), format='gro')


def _is_float(s: str) -> bool:
    """检查字符串是否可转为浮点数"""
    try:
        float(s)
        return True
    except ValueError:
        return False


_ATOMIC_SYMBOLS = {
    1: "H", 2: "He", 3: "Li", 4: "Be", 5: "B", 6: "C", 7: "N", 8: "O",
    9: "F", 10: "Ne", 11: "Na", 12: "Mg", 13: "Al", 14: "Si", 15: "P",
    16: "S", 17: "Cl", 18: "Ar", 19: "K", 20: "Ca", 21: "Sc", 22: "Ti",
    23: "V", 24: "Cr", 25: "Mn", 26: "Fe", 27: "Co", 28: "Ni", 29: "Cu",
    30: "Zn", 31: "Ga", 32: "Ge", 33: "As", 34: "Se", 35: "Br", 36: "Kr",
    37: "Rb", 38: "Sr", 39: "Y", 40: "Zr", 41: "Nb", 42: "Mo", 44: "Ru",
    45: "Rh", 46: "Pd", 47: "Ag", 48: "Cd", 49: "In", 50: "Sn", 51: "Sb",
    52: "Te", 53: "I", 54: "Xe", 55: "Cs", 56: "Ba", 57: "La", 72: "Hf",
    73: "Ta", 74: "W", 75: "Re", 76: "Os", 77: "Ir", 78: "Pt", 79: "Au",
    80: "Hg", 81: "Tl", 82: "Pb", 83: "Bi",
}


def _atomic_number_to_symbol(z: int) -> str:
    """原子序数转元素符号"""
    return _ATOMIC_SYMBOLS.get(z, f"X{z}")


def read_structure(filepath: str, format: Optional[str] = None) -> Structure:
    """
    读取结构文件的便捷函数

    Args:
        filepath: 文件路径
        format: 文件格式

    Returns:
        Structure对象
    """
    reader = StructureReader()
    return reader.read(filepath, format)


def extract_molecule_info(filepath: str) -> MoleculeInfo:
    """
    从文件提取分子信息

    Args:
        filepath: 文件路径

    Returns:
        MoleculeInfo对象
    """
    structure = read_structure(filepath)
    return MoleculeInfo.from_structure(structure, name=Path(filepath).stem)
