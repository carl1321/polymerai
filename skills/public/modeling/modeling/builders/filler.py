"""
Filler - 分子填充构建器

封装 Packmol 对已有盒子填充分子。支持简单 Recipe 形式
(`molecule` + `density` / `count`) 与进阶 `requests` 列表两种入口。
"""

from __future__ import annotations
from typing import List, Optional, Dict, Any, Tuple, Union
from dataclasses import dataclass
from enum import Enum
import numpy as np

from modeling.builders.base import BaseBuilder
from modeling.core.structure import Structure, merge_structures


class RegionType(Enum):
    BOX = "box"
    SPHERE = "sphere"
    CYLINDER = "cylinder"


@dataclass
class FillRegion:
    type: RegionType
    params: Dict[str, Any]
    inside: bool = True

    @classmethod
    def box(cls, xmin, ymin, zmin, xmax, ymax, zmax, inside=True) -> "FillRegion":
        return cls(type=RegionType.BOX,
                   params={"xmin": xmin, "ymin": ymin, "zmin": zmin,
                           "xmax": xmax, "ymax": ymax, "zmax": zmax},
                   inside=inside)

    @classmethod
    def cylinder(cls, x, y, z1, z2, radius, inside=True) -> "FillRegion":
        return cls(type=RegionType.CYLINDER,
                   params={"x": x, "y": y, "z1": z1, "z2": z2, "radius": radius},
                   inside=inside)

    @classmethod
    def sphere(cls, x, y, z, radius, inside=True) -> "FillRegion":
        return cls(type=RegionType.SPHERE,
                   params={"x": x, "y": y, "z": z, "radius": radius},
                   inside=inside)

    def to_packmol_constraint(self) -> str:
        p = self.params
        keyword = "inside" if self.inside else "outside"
        if self.type == RegionType.BOX:
            return (f"{keyword} box {p['xmin']} {p['ymin']} {p['zmin']} "
                    f"{p['xmax']} {p['ymax']} {p['zmax']}")
        elif self.type == RegionType.CYLINDER:
            return (f"{keyword} cylinder {p['x']} {p['y']} {p['z1']} "
                    f"{p['x']} {p['y']} {p['z2']} {p['radius']}")
        elif self.type == RegionType.SPHERE:
            return f"{keyword} sphere {p['x']} {p['y']} {p['z']} {p['radius']}"


@dataclass
class FillRequest:
    molecule: Structure
    count: Optional[int] = None
    density: Optional[float] = None
    regions: List[FillRegion] = None

    def __post_init__(self):
        if self.regions is None:
            self.regions = []


# 常用分子在 300 K 下的密度 (g/cm³)，用于 density→count 换算
_DEFAULT_DENSITY = {
    "water": 1.0, "h2o": 1.0,
    "ethanol": 0.789, "c2h5oh": 0.789,
    "methane": 0.4226,
    "methanol": 0.7918,
    "benzene": 0.8765,
    "acetone": 0.7845,
}


class Filler(BaseBuilder):
    """
    分子填充构建器（Packmol 后端）。

    两种调用方式:

    1. Recipe 简单形式（Recipe 3 / 6）:
       ``params = {"molecule": "water", "density": 1.0}``
       上一步的 Structure 提供盒子 cell；density 换算成 count。

    2. 进阶形式:
       ``params = {"requests": [FillRequest(...), ...]}``
       允许多分子、自定义区域。

    参数:
        molecule: 分子名（BuiltinMolecules 或 ase.build.molecule）或 Structure
        density:  g/cm³，与 count 二选一（填充整盒时使用）
        count:    分子数量，与 density 二选一
        region:   字符串约束，目前支持 None / "above_slab"
        requests: 进阶模式下的 FillRequest 列表
        tolerance: Packmol 原子间最小距离 (Å)，默认 2.0
        seed:     随机种子，-1 随机
    """

    name = "filler"
    accepts_prev = True
    required_params: list = []  # molecule 或 requests 二选一，在 build 内校验
    default_params = {
        "molecule": None,
        "density": None,
        "count": None,
        "region": None,
        "requests": None,
        "tolerance": 2.0,
        "seed": -1,
        "maxit": 20,
    }

    def build(
        self,
        molecule=None,
        density: Optional[float] = None,
        count: Optional[int] = None,
        region: Optional[Union[str, Dict]] = None,
        requests: Optional[List[FillRequest]] = None,
        tolerance: float = 2.0,
        seed: int = -1,
        maxit: int = 20,
        prev: Optional[Structure] = None,
        **kwargs,
    ) -> Structure:
        if prev is None or prev.cell is None:
            raise ValueError(
                "Filler needs a preceding step that produced a box with a cell "
                "(e.g. box builder). Put a `box` step before `filler` in the Recipe."
            )

        box_cell = np.asarray(prev.cell, dtype=float)
        if box_cell.ndim == 1:
            box_cell = np.diag(box_cell)

        if requests is None:
            if molecule is None:
                raise ValueError("Filler: need either `molecule` or `requests`")
            requests = [self._simple_request(molecule, density, count,
                                             region, box_cell)]

        from modeling.tools.packmol_tools import PackmolTools
        PackmolTools.require_packmol()

        filled = PackmolTools.run(
            requests=requests,
            output_file="filled.pdb",
            tolerance=tolerance,
            seed=seed,
            maxit=maxit,
        )
        filled.cell = box_cell
        filled.pbc = list(prev.pbc)

        if prev.n_atoms > 0:
            filled = merge_structures([prev, filled], name=f"{prev.name}_filled")
            filled.cell = box_cell
            filled.pbc = list(prev.pbc)
        else:
            filled.name = f"{prev.name}_filled" if prev.name else "filled_box"

        return filled

    def _simple_request(
        self,
        molecule,
        density: Optional[float],
        count: Optional[int],
        region: Optional[Union[str, Dict]],
        box_cell: np.ndarray,
    ) -> FillRequest:
        mol_struct, mol_name = self._resolve_molecule(molecule)

        if count is None:
            if density is None:
                density = _DEFAULT_DENSITY.get(mol_name.lower())
                if density is None:
                    raise ValueError(
                        f"Filler: must specify `count` or `density` for '{mol_name}'"
                    )
            count = self._count_from_density(mol_struct, density, box_cell, region)

        regions = self._region_constraints(region, box_cell)
        return FillRequest(molecule=mol_struct, count=count, regions=regions)

    @staticmethod
    def _resolve_molecule(molecule) -> Tuple[Structure, str]:
        if isinstance(molecule, Structure):
            return molecule, molecule.name or "mol"
        if isinstance(molecule, str):
            from modeling.resources.molecules import BuiltinMolecules
            try:
                return BuiltinMolecules.get(molecule), molecule
            except KeyError:
                pass
            from modeling.tools.ase_tools import ASETools
            try:
                return ASETools.build_molecule(molecule), molecule
            except Exception as e:
                raise ValueError(f"Unknown molecule '{molecule}': {e}")
        raise TypeError(f"molecule must be str or Structure, got {type(molecule)}")

    @staticmethod
    def _count_from_density(
        mol: Structure,
        density: float,
        box_cell: np.ndarray,
        region: Optional[Union[str, Dict]],
    ) -> int:
        volume_A3 = float(abs(np.linalg.det(box_cell)))
        if isinstance(region, str) and region == "above_slab":
            # 近似：假设 slab 占据下半 c 轴
            volume_A3 *= 0.5
        volume_cm3 = volume_A3 * 1e-24

        try:
            from ase.data import atomic_masses, atomic_numbers
            masses = [atomic_masses[atomic_numbers[s]] for s in mol.symbols]
            mol_mass_amu = float(sum(masses))
        except Exception:
            mol_mass_amu = 18.015  # water fallback

        avogadro = 6.02214076e23
        grams_per_molecule = mol_mass_amu / avogadro
        count = int(round(density * volume_cm3 / grams_per_molecule))
        if count < 1:
            raise ValueError(
                f"Density→count returned {count} molecules; box too small "
                f"(V={volume_A3:.1f} Å³) or density {density} g/cm³ is off."
            )
        return count

    @staticmethod
    def _region_constraints(
        region: Optional[Union[str, Dict]], box_cell: np.ndarray
    ) -> List[FillRegion]:
        a, b, c = box_cell[0, 0], box_cell[1, 1], box_cell[2, 2]
        pad = 1.0  # 留出 1 Å 边距避免原子贴壁
        if region is None:
            return [FillRegion.box(pad, pad, pad, a - pad, b - pad, c - pad)]
        if region == "above_slab":
            return [FillRegion.box(pad, pad, c * 0.5, a - pad, b - pad, c - pad)]
        if isinstance(region, dict):
            kind = region.get("type")
            if kind == "box":
                return [FillRegion.box(**{k: region[k] for k in
                                          ("xmin", "ymin", "zmin", "xmax", "ymax", "zmax")})]
            if kind == "sphere":
                return [FillRegion.sphere(region["x"], region["y"], region["z"],
                                          region["radius"])]
            if kind == "cylinder":
                return [FillRegion.cylinder(region["x"], region["y"],
                                            region["z1"], region["z2"],
                                            region["radius"])]
        raise ValueError(f"Unsupported region spec: {region!r}")
