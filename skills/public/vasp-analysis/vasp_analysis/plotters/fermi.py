"""Fermi surface (2D / 3D) via pyprocar."""
from __future__ import annotations

from pathlib import Path

from .base import resolve_output


def plot(
    workdir: str | Path,
    *,
    dim: str = "3d",
    out: str | Path | None = None,
    fmt: str = "png",
) -> Path:
    import pyprocar  # type: ignore

    workdir = Path(workdir)
    out_path = Path(out) if out else resolve_output(workdir, f"fermi_{dim}", fmt)

    if dim == "3d":
        pyprocar.fermi3D(
            code="vasp",
            dirname=str(workdir),
            mode="plain",
            show=False,
            savefig=str(out_path),
        )
    else:
        pyprocar.fermi2D(
            code="vasp",
            dirname=str(workdir),
            mode="plain",
            show=False,
            savefig=str(out_path),
        )
    return out_path
