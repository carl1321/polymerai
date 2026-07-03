"""Density of states plot — primary backend: sumo-dosplot."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .base import apply_style, resolve_output


def plot(
    workdir: str | Path,
    *,
    orbital: bool = False,
    element: bool = False,
    out: str | Path | None = None,
    fmt: str = "png",
    fallback: bool = True,
) -> Path:
    workdir = Path(workdir)
    out_path = Path(out) if out else resolve_output(workdir, "dos", fmt)

    if shutil.which("sumo-dosplot"):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        prefix = out_path.stem
        cmd = [
            "sumo-dosplot",
            "-f", str(workdir / "vasprun.xml"),
            "-d", str(out_path.parent),
            "-p", prefix,
            "--format", fmt,
        ]
        if orbital:
            cmd.append("--orbitals")
        if element:
            cmd.append("--elements")
        subprocess.run(cmd, check=True)
        generated = out_path.parent / f"{prefix}_dos.{fmt}"
        if generated.exists() and generated != out_path:
            shutil.move(str(generated), str(out_path))
        return out_path

    if not fallback:
        raise RuntimeError("sumo-dosplot not on PATH and fallback disabled")

    return _pymatgen_dos(workdir, out_path, orbital=orbital, element=element)


def _pymatgen_dos(workdir: Path, out_path: Path, *, orbital: bool, element: bool) -> Path:
    import matplotlib.pyplot as plt
    from pymatgen.electronic_structure.plotter import DosPlotter
    from pymatgen.io.vasp import Vasprun

    apply_style()
    vrun = Vasprun(str(workdir / "vasprun.xml"))
    cdos = vrun.complete_dos
    plotter = DosPlotter()
    plotter.add_dos("Total DOS", cdos)
    if element:
        for el, dos in cdos.get_element_dos().items():
            plotter.add_dos(str(el), dos)
    if orbital:
        for site, sdos in cdos.get_site_orbital_dos(cdos.structure[0], 0).items():
            plotter.add_dos(f"orb-{site}", sdos)
    fig = plotter.get_plot()
    fig.savefig(out_path)
    plt.close("all")
    return out_path
