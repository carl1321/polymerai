"""POTCAR generation: enforce vasp-potcar first, then optional fallback."""

from __future__ import annotations

import shutil
import subprocess
import os
from pathlib import Path

_DEFAULT_PP_CANDIDATES = [
    Path("/mnt/skills/public/pot5.4"),
    Path(__file__).resolve().parents[1] / "pot5.4",
]


def _resolve_default_pp_path() -> Path | None:
    for candidate in _DEFAULT_PP_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def generate_potcar(
    poscar: Path,
    work_dir: Path,
    functional: str = "PBE",
    backend: str = "vasp-potcar",
) -> Path:
    """Write POTCAR into work_dir. Returns the path."""
    potcar_path = work_dir / "POTCAR"
    if potcar_path.exists():
        return potcar_path
    source_marker = work_dir / ".potcar_source"
    if backend == "vasp-potcar":
        # Hard rule: always try vasp-potcar first, then fallback only if it fails.
        try:
            _call_vasp_potcar(poscar, potcar_path, functional)
            source_marker.write_text("vasp-potcar\n", encoding="utf-8")
            return potcar_path
        except Exception as exc:
            _pymatgen_fallback(poscar, potcar_path, functional)
            source_marker.write_text(f"pymatgen-fallback\nreason={exc}\n", encoding="utf-8")
            return potcar_path

    _pymatgen_fallback(poscar, potcar_path, functional)
    source_marker.write_text("pymatgen\n", encoding="utf-8")
    return potcar_path


def _call_vasp_potcar(poscar: Path, out: Path, functional: str) -> None:
    if shutil.which("vasp-potcar") is None:
        raise FileNotFoundError("vasp-potcar command not found in PATH")
    if not os.environ.get("VASP_PP_PATH"):
        default_pp = _resolve_default_pp_path()
        if default_pp is not None:
            os.environ["VASP_PP_PATH"] = str(default_pp)
    cmd = ["vasp-potcar", "workflow", str(poscar), "--output", str(out), "--functional", functional]
    subprocess.run(cmd, check=True)


def _pymatgen_fallback(poscar: Path, out: Path, functional: str) -> None:
    from pymatgen.core import Structure
    from pymatgen.io.vasp.inputs import Potcar

    if not os.environ.get("PMG_VASP_PSP_DIR"):
        default_pp = _resolve_default_pp_path()
        if default_pp is not None:
            os.environ["PMG_VASP_PSP_DIR"] = str(default_pp)

    structure = Structure.from_file(str(poscar))
    symbols = [site.specie.symbol for site in structure.sites]
    dedup: list[str] = []
    for s in symbols:
        if not dedup or dedup[-1] != s:
            dedup.append(s)
    potcar = Potcar(symbols=dedup, functional=functional)
    potcar.write_file(str(out))
