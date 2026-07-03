"""KPOINTS generation: Bravais-aware mesh + seekpath line-mode."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _reciprocal_density_mesh(structure, density: int, force_gamma: bool) -> list[int]:
    """Simple reciprocal-density mesh (mimics pymatgen Kpoints.automatic_density)."""
    from pymatgen.io.vasp import Kpoints

    k = Kpoints.automatic_density(structure, kppa=density, force_gamma=force_gamma)
    return list(k.kpts[0])


def mesh(
    structure,
    *,
    density: int = 1000,
    gamma_required: bool = False,
) -> "Kpoints":
    """Return a `pymatgen.io.vasp.Kpoints` uniform mesh."""
    from pymatgen.io.vasp import Kpoints

    return Kpoints.automatic_density(structure, kppa=density, force_gamma=gamma_required)


def line_mode(structure, *, density: int = 50) -> "Kpoints":
    """Seekpath-style high-symmetry path for band structure."""
    from pymatgen.io.vasp import Kpoints
    from pymatgen.symmetry.bandstructure import HighSymmKpath

    path = HighSymmKpath(structure)
    return Kpoints.automatic_linemode(density, path)


def kpoints_opt_for_hse(mesh_kp: "Kpoints", line_kp: "Kpoints", out_dir: Path) -> Path:
    """Write KPOINTS_OPT (VASP 6.3+) containing the band-path, keeping KPOINTS as mesh.

    Returns the KPOINTS_OPT path.
    """
    out_path = Path(out_dir) / "KPOINTS_OPT"
    line_kp.write_file(str(out_path))
    return out_path


def fallback_zero_weight(mesh_kp: "Kpoints", line_kp: "Kpoints"):
    """Combine mesh (SCF weights) + line-mode (zero weight) for HSE pre-6.3."""
    from pymatgen.io.vasp import Kpoints

    # Expand mesh to explicit k-points with weights 1
    mesh_abc = mesh_kp.kpts[0]
    explicit: list[tuple[list[float], int]] = []
    # naive expansion: Γ-centered grid
    nx, ny, nz = mesh_abc
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                explicit.append(([i / nx, j / ny, k / nz], 1))
    # Add line-mode k-points at weight 0 (linemode Kpoints keeps endpoints in kpts)
    for kp in line_kp.kpts:
        explicit.append((list(kp), 0))

    combined = Kpoints(
        comment="SCF mesh + zero-weight band path (HSE fallback)",
        num_kpts=len(explicit),
        style=Kpoints.supported_modes.Reciprocal,
        kpts=[pt for pt, _ in explicit],
        kpts_weights=[w for _, w in explicit],
    )
    return combined


def write(kp: "Kpoints", out_dir: str | Path, name: str = "KPOINTS") -> Path:
    out = Path(out_dir) / name
    out.parent.mkdir(parents=True, exist_ok=True)
    kp.write_file(str(out))
    return out


_ = Any  # re-exported for type hints
