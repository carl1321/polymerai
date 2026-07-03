"""Phonon dispersion + DOS via sumo-phonon-bandplot (assumes phonopy outputs present)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .base import resolve_output


def plot(
    workdir: str | Path,
    *,
    supercell: tuple[int, int, int] = (2, 2, 2),
    mode: str = "finite",
    out: str | Path | None = None,
    fmt: str = "png",
) -> Path:
    workdir = Path(workdir)
    out_path = Path(out) if out else resolve_output(workdir, "phonon", fmt)

    band_yaml = workdir / "band.yaml"
    if not band_yaml.is_file():
        raise FileNotFoundError(
            f"{band_yaml} not found — run phonopy first (workflows/phonon_pipeline.py "
            "can do it given FORCE_SETS or DFPT vasprun.xml)."
        )

    if not shutil.which("sumo-phonon-bandplot"):
        raise RuntimeError("sumo-phonon-bandplot required for phonon plots")

    cmd = ["sumo-phonon-bandplot",
           "--filename", str(band_yaml),
           "--image-format", fmt,
           "--output", str(out_path)]
    subprocess.run(cmd, check=True)
    _ = supercell, mode  # informational only; phonopy already encodes them
    return out_path
