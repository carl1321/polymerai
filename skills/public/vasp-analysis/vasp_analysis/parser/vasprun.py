"""vasprun.xml convenience wrapper."""
from __future__ import annotations

from functools import cached_property
from pathlib import Path


class VasprunWrapper:
    """Lazy wrapper around pymatgen.io.vasp.Vasprun."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(self.path)

    @cached_property
    def _vasprun(self):
        from pymatgen.io.vasp import Vasprun

        return Vasprun(str(self.path), parse_projected_eigen=True)

    @property
    def structure(self):
        return self._vasprun.final_structure

    @property
    def total_energy(self) -> float:
        return float(self._vasprun.final_energy)

    @property
    def band_gap(self) -> float | None:
        try:
            bs = self._vasprun.get_band_structure(line_mode=False)
            return float(bs.get_band_gap()["energy"])
        except Exception:
            return None

    @property
    def is_metal(self) -> bool | None:
        gap = self.band_gap
        if gap is None:
            return None
        return gap < 1e-4

    @property
    def magnetization(self) -> float | None:
        try:
            outcar = self.path.parent / "OUTCAR"
            if not outcar.is_file():
                return None
            from pymatgen.io.vasp import Outcar

            return float(Outcar(str(outcar)).total_mag or 0.0)
        except Exception:
            return None

    @property
    def converged(self) -> bool:
        return bool(self._vasprun.converged_electronic and self._vasprun.converged_ionic)

    @property
    def incar(self) -> dict:
        return dict(self._vasprun.incar)
