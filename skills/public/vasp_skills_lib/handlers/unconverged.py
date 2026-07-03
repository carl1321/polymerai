"""Unconverged-run handler: limited auto-correction for SCF/ionic non-convergence."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


_NELM_RE = re.compile(r"NELM\s*=\s*(\d+)", re.I)
_DAV_RE = re.compile(r"^\s*DAV:", re.M)
_RMM_RE = re.compile(r"^\s*RMM:", re.M)
_REACHED_RE = re.compile(r"reached required accuracy", re.I)


class UnconvergedHandler:
    """Detect electronic/ionic non-convergence and apply safe INCAR patches.

    Strategy ladder (tried in order, one per invocation):
      1. Increase NELM (electronic SCF limit)
      2. Switch ALGO Fast → Normal
      3. Reduce POTIM for ionic relaxation
    """

    _STRATEGIES = [
        {"NELM": 200},
        {"ALGO": "Normal"},
        {"POTIM": 0.1},
    ]

    def __init__(self, work_dir: Path, max_corrections: int = 3):
        self.work_dir = Path(work_dir)
        self.max_corrections = max_corrections
        self._attempt = 0
        self._detected = False

    def _is_unconverged(self) -> bool:
        oszicar = self.work_dir / "OSZICAR"
        vasp_out = self.work_dir / "vasp.out"
        blob = ""
        for f in (oszicar, vasp_out):
            if f.exists():
                try:
                    blob += f.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
        if not blob:
            return False
        if _REACHED_RE.search(blob):
            return False
        e_steps = len(_DAV_RE.findall(blob)) + len(_RMM_RE.findall(blob))
        if e_steps == 0:
            return False
        nelm = 60
        incar = self.work_dir / "INCAR"
        if incar.exists():
            try:
                m = _NELM_RE.search(incar.read_text(encoding="utf-8", errors="replace"))
                if m:
                    nelm = int(m.group(1))
            except Exception:
                pass
        return e_steps >= nelm

    def check(self) -> bool:
        self._detected = self._is_unconverged()
        return self._detected and self._attempt < self.max_corrections

    def correct(self) -> dict[str, Any]:
        if not self._detected or self._attempt >= self.max_corrections:
            return {"detected": ["unconverged"] if self._detected else [], "applied": []}
        strategy = self._STRATEGIES[min(self._attempt, len(self._STRATEGIES) - 1)]
        self._attempt += 1
        incar_path = self.work_dir / "INCAR"
        if incar_path.exists():
            try:
                from pymatgen.io.vasp.inputs import Incar

                incar = Incar.from_file(str(incar_path))
                incar.update(strategy)
                incar.write_file(str(incar_path))
            except Exception:
                pass
        return {
            "detected": ["unconverged"],
            "applied": [
                {
                    "error": "unconverged",
                    "severity": "medium",
                    "fix": f"apply {strategy}",
                    "incar_updates": strategy,
                }
            ],
        }
