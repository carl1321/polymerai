"""Phonopy pipeline: vasprun.xml(s) → FORCE_SETS → band.yaml.

Wraps the standard ``phonopy`` CLI. Two modes:

- ``finite``: requires sub-directories ``disp-001/``, ``disp-002/`` … each with
  vasprun.xml from a finite-displacement static calc.
- ``dfpt``: requires a single ``vasprun.xml`` from an IBRION=8 / DFPT calc.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def run(
    workdir: str | Path,
    *,
    supercell: tuple[int, int, int] = (2, 2, 2),
    mode: str = "finite",
) -> Path:
    workdir = Path(workdir)
    if not shutil.which("phonopy"):
        raise RuntimeError("phonopy CLI not on PATH")

    sc = " ".join(str(s) for s in supercell)

    if mode == "finite":
        disp_runs = sorted(workdir.glob("disp-*/vasprun.xml"))
        if not disp_runs:
            raise FileNotFoundError(f"No disp-*/vasprun.xml under {workdir}")
        cmd = ["phonopy", "-f", *map(str, disp_runs)]
        subprocess.run(cmd, check=True, cwd=workdir)
    elif mode == "dfpt":
        vrun = workdir / "vasprun.xml"
        if not vrun.is_file():
            raise FileNotFoundError(vrun)
        subprocess.run(["phonopy", "--fc", str(vrun)], check=True, cwd=workdir)
    else:
        raise ValueError(f"Unknown phonon mode: {mode}")

    band_conf = workdir / "band.conf"
    if not band_conf.is_file():
        band_conf.write_text(
            f"DIM = {sc}\nBAND = AUTO\nBAND_POINTS = 101\n",
            encoding="utf-8",
        )
    subprocess.run(["phonopy", "-p", "-s", str(band_conf)], check=True, cwd=workdir)

    band_yaml = workdir / "band.yaml"
    if not band_yaml.is_file():
        raise RuntimeError("phonopy did not produce band.yaml")
    return band_yaml
