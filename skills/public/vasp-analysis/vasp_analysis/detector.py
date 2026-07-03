"""Auto-detect VASP calculation type from a work directory."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

CALC_TYPES = (
    "band", "dos", "band_dos", "phonon", "elastic",
    "optical", "defect", "static", "relax", "unknown",
)


@dataclass
class DetectionResult:
    calc_type: str
    workdir: Path
    notes: list[str]

    def __str__(self) -> str:
        n = "; ".join(self.notes) if self.notes else "n/a"
        return f"DetectionResult(calc_type={self.calc_type}, notes=[{n}])"


def _has_line_mode_kpoints(kpoints: Path) -> bool:
    if not kpoints.is_file():
        return False
    try:
        text = kpoints.read_text(errors="ignore").splitlines()
    except OSError:
        return False
    for line in text[:5]:
        s = line.strip().lower()
        if s.startswith("l") and "line" in s:
            return True
        if s == "l":
            return True
    return False


def _outcar_mentions(outcar: Path, needle: str) -> bool:
    if not outcar.is_file():
        return False
    try:
        with outcar.open("r", errors="ignore") as f:
            for line in f:
                if needle in line:
                    return True
    except OSError:
        return False
    return False


def _vasprun_flag(vasprun: Path, tag: str) -> str | None:
    if not vasprun.is_file():
        return None
    try:
        for line in vasprun.open("r", errors="ignore"):
            if f'name="{tag}"' in line:
                return line.strip()
    except OSError:
        return None
    return None


def detect(workdir: str | Path) -> DetectionResult:
    """Inspect a VASP work directory and return a best-guess calculation type."""
    workdir = Path(workdir)
    notes: list[str] = []
    kpoints = workdir / "KPOINTS"
    outcar = workdir / "OUTCAR"
    vasprun = workdir / "vasprun.xml"
    doscar = workdir / "DOSCAR"
    incar = workdir / "INCAR"

    # phonon markers take priority (phonopy produces band.yaml / FORCE_SETS /
    # FORCE_CONSTANTS even without a VASP run in this directory).
    if any((workdir / n).exists() for n in ("band.yaml", "FORCE_SETS", "FORCE_CONSTANTS", "mesh.yaml")):
        notes.append("phonopy output detected")
        return DetectionResult("phonon", workdir, notes)

    if _outcar_mentions(outcar, "ELASTIC MODULI"):
        notes.append("OUTCAR contains ELASTIC MODULI")
        return DetectionResult("elastic", workdir, notes)

    incar_text = incar.read_text(errors="ignore").upper() if incar.is_file() else ""
    if "LOPTICS" in incar_text and "=T" in incar_text.replace(" ", ""):
        notes.append("INCAR LOPTICS=T")
        return DetectionResult("optical", workdir, notes)

    line_mode = _has_line_mode_kpoints(kpoints)
    if line_mode:
        notes.append("KPOINTS line-mode")
        if doscar.is_file() and doscar.stat().st_size > 10_000:
            return DetectionResult("band_dos", workdir, notes)
        return DetectionResult("band", workdir, notes)

    if doscar.is_file() and doscar.stat().st_size > 10_000:
        notes.append("DOSCAR populated")
        return DetectionResult("dos", workdir, notes)

    if "IBRION" in incar_text:
        if "NSW" in incar_text:
            notes.append("INCAR has NSW")
            return DetectionResult("relax", workdir, notes)
        notes.append("INCAR has IBRION")
        return DetectionResult("static", workdir, notes)

    if vasprun.is_file():
        notes.append("vasprun.xml present but no strong signal")
        return DetectionResult("static", workdir, notes)

    notes.append("no recognisable VASP outputs")
    return DetectionResult("unknown", workdir, notes)
