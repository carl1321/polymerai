"""OUTCAR convenience wrapper."""
from __future__ import annotations

from functools import cached_property
from pathlib import Path


class OutcarWrapper:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(self.path)

    @cached_property
    def _outcar(self):
        from pymatgen.io.vasp import Outcar

        return Outcar(str(self.path))

    @property
    def total_mag(self) -> float:
        return float(self._outcar.total_mag or 0.0)

    @cached_property
    def elastic_tensor(self):
        """Read elastic moduli (kBar) from OUTCAR and return a 6x6 numpy matrix in GPa."""
        import numpy as np

        rows: list[list[float]] = []
        capture = False
        with self.path.open("r", errors="ignore") as f:
            for line in f:
                if "TOTAL ELASTIC MODULI" in line:
                    capture = True
                    rows = []
                    continue
                if capture:
                    stripped = line.strip()
                    if stripped.startswith(("XX", "YY", "ZZ", "XY", "YZ", "ZX")):
                        parts = stripped.split()
                        rows.append([float(x) / 10.0 for x in parts[1:7]])  # kBar -> GPa
                        if len(rows) == 6:
                            break
        if len(rows) != 6:
            raise ValueError("No TOTAL ELASTIC MODULI block found in OUTCAR")
        return np.array(rows)
