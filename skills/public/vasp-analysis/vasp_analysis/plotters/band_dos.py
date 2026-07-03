"""Combined band + DOS plot — sumo-bandplot --dos."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .base import resolve_output


def plot(
    workdir: str | Path,
    *,
    out: str | Path | None = None,
    fmt: str = "png",
) -> Path:
    workdir = Path(workdir)
    out_path = Path(out) if out else resolve_output(workdir, "band_dos", fmt)
    if not shutil.which("sumo-bandplot"):
        raise RuntimeError("sumo-bandplot required for combined band+DOS plot")
    cmd = ["sumo-bandplot",
           "--directory", str(workdir),
           "--dos", str(workdir / "vasprun.xml"),
           "--image-format", fmt,
           "--output", str(out_path)]
    subprocess.run(cmd, check=True)
    return out_path
