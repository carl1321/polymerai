"""Optical absorption / dielectric function — sumo-optplot."""
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
    out_path = Path(out) if out else resolve_output(workdir, "optical", fmt)
    if not shutil.which("sumo-optplot"):
        raise RuntimeError("sumo-optplot required for optical plots")
    cmd = ["sumo-optplot",
           "--filenames", str(workdir / "vasprun.xml"),
           "--image-format", fmt,
           "--output", str(out_path)]
    subprocess.run(cmd, check=True)
    return out_path
