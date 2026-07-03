"""Electronic band structure plot — primary backend: sumo-bandplot."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .base import apply_style, resolve_output


def plot(
    workdir: str | Path,
    *,
    projected: bool = False,
    out: str | Path | None = None,
    fmt: str = "png",
    fallback: bool = True,
) -> Path:
    """Plot a band structure from `workdir/vasprun.xml`.

    Tries ``sumo-bandplot`` first; falls back to pymatgen's BSPlotter if
    sumo is unavailable and ``fallback=True``.
    """
    workdir = Path(workdir)
    out_path = Path(out) if out else resolve_output(workdir, "band", fmt)

    if shutil.which("sumo-bandplot"):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        prefix = out_path.stem
        cmd = [
            "sumo-bandplot",
            "-f", str(workdir / "vasprun.xml"),
            "-d", str(out_path.parent),
            "-p", prefix,
            "--format", fmt,
        ]
        if projected:
            cmd.extend(["--project", "element"])
        subprocess.run(cmd, check=True)
        # sumo appends "_band" to prefix: prefix_band.fmt
        generated = out_path.parent / f"{prefix}_band.{fmt}"
        if generated.exists() and generated != out_path:
            shutil.move(str(generated), str(out_path))
        return out_path

    if not fallback:
        raise RuntimeError("sumo-bandplot not on PATH and fallback disabled")

    return _pymatgen_band(workdir, out_path)


def _pymatgen_band(workdir: Path, out_path: Path) -> Path:
    import matplotlib.pyplot as plt
    from pymatgen.electronic_structure.plotter import BSPlotter
    from pymatgen.io.vasp import Vasprun

    apply_style()
    vrun = Vasprun(str(workdir / "vasprun.xml"), parse_projected_eigen=False)
    bs = vrun.get_band_structure(line_mode=True)
    plotter = BSPlotter(bs)
    fig = plotter.get_plot()
    fig.savefig(out_path)
    plt.close("all")
    return out_path
