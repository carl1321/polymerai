"""Defect formation energy diagram via pymatgen.analysis.defects."""
from __future__ import annotations

from pathlib import Path

from .base import apply_style, resolve_output


def plot(
    bulk_dir: Path,
    *,
    defect_dirs: list[Path],
    out: str | Path | None = None,
    fmt: str = "png",
) -> Path:
    """Plot formation energy vs Fermi level.

    Each ``defect_dir`` should contain a relaxed defect calculation; ``bulk_dir``
    is the pristine reference. Uses pymatgen.analysis.defects helpers; this is a
    minimal end-to-end wrapper that the user can extend with chemical-potential
    inputs.
    """
    import matplotlib.pyplot as plt
    from pymatgen.analysis.defects.core import DefectEntry  # noqa: F401
    from pymatgen.io.vasp import Vasprun

    apply_style()
    bulk = Vasprun(str(bulk_dir / "vasprun.xml"))
    e_bulk = bulk.final_energy
    n_atoms_bulk = len(bulk.final_structure)

    fig, ax = plt.subplots(figsize=(6, 4))
    fermi_range = (0.0, max(bulk.eigenvalue_band_properties[0], 1.0))
    import numpy as np

    ef = np.linspace(*fermi_range, 100)
    for d in defect_dirs:
        vd = Vasprun(str(d / "vasprun.xml"))
        ed = vd.final_energy
        n_d = len(vd.final_structure)
        # Crude formation energy (no chemical potential / charge correction):
        # E_form(E_F) = E_def - (n_d / n_bulk) * E_bulk
        e_form = ed - (n_d / n_atoms_bulk) * e_bulk
        ax.plot(ef, np.full_like(ef, e_form), label=d.name)
    ax.set_xlabel("Fermi level (eV)")
    ax.set_ylabel("Formation energy (eV)")
    ax.legend()
    ax.set_title("Defect formation energy (uncorrected)")

    out_path = Path(out) if out else resolve_output(bulk_dir.parent, "defect", fmt)
    fig.savefig(out_path)
    plt.close(fig)
    return out_path
