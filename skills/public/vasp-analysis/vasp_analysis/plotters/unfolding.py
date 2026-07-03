"""Band unfolding via pyprocar."""
from __future__ import annotations

from pathlib import Path

from .base import resolve_output


def plot(
    workdir: str | Path,
    *,
    supercell: tuple[int, int, int] = (2, 2, 2),
    out: str | Path | None = None,
    fmt: str = "png",
) -> Path:
    import numpy as np
    import pyprocar  # type: ignore

    workdir = Path(workdir)
    out_path = Path(out) if out else resolve_output(workdir, "unfolding", fmt)
    transformation = np.diag(supercell)
    pyprocar.unfold(
        code="vasp",
        dirname=str(workdir),
        mode="plain",
        transformation_matrix=transformation,
        show=False,
        savefig=str(out_path),
    )
    return out_path
