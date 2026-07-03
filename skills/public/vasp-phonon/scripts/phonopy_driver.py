"""Phonopy driver — thin wrapper around phonopy's Python API.

Phonopy owns the supercell construction (symmetry-reduced displacements). We
call phonopy to:
  1. Build symmetry-reduced displaced supercells (`phonopy -d --dim=...`)
  2. Collect forces from finished VASP runs into FORCE_SETS
  3. Compute phonon bands / DOS / thermodynamics

Note: phonopy's supercell is physics-driven and intentionally does NOT go
through the `modeling` skill.
"""

from __future__ import annotations

from pathlib import Path


def generate_displacements(unitcell_poscar: Path, work_dir: Path,
                           supercell: tuple[int, int, int] = (2, 2, 2),
                           displacement: float = 0.01) -> list[Path]:
    """Write SPOSCAR + POSCAR-00N files into work_dir. Return list of displaced POSCARs."""
    from phonopy import Phonopy
    from phonopy.interface.vasp import read_vasp, write_vasp
    import numpy as np

    unit = read_vasp(str(unitcell_poscar))
    phonon = Phonopy(unit, supercell_matrix=np.diag(list(supercell)))
    phonon.generate_displacements(distance=displacement)
    supercells = phonon.supercells_with_displacements

    work_dir.mkdir(parents=True, exist_ok=True)
    write_vasp(str(work_dir / "SPOSCAR"), phonon.supercell)
    paths: list[Path] = []
    for i, sc in enumerate(supercells, start=1):
        fname = work_dir / f"POSCAR-{i:03d}"
        write_vasp(str(fname), sc)
        paths.append(fname)

    # Save phonon object state (disp.yaml) for later FORCE_SETS collection
    phonon.save(str(work_dir / "phonopy_disp.yaml"))
    return paths


def collect_forces(work_dir: Path, vasprun_files: list[Path]) -> Path:
    """Given completed VASP runs, assemble FORCE_SETS."""
    import subprocess
    args = ["phonopy", "-f"] + [str(v) for v in vasprun_files]
    subprocess.run(args, cwd=str(work_dir), check=True)
    return work_dir / "FORCE_SETS"


def compute_bands_dos(work_dir: Path, mesh: tuple[int, int, int] = (31, 31, 31)) -> dict:
    """Use phonopy to compute bands + DOS. Writes band.yaml, total_dos.dat."""
    from phonopy import load
    phonon = load(str(work_dir / "phonopy_disp.yaml"),
                  force_sets_filename=str(work_dir / "FORCE_SETS"))
    phonon.run_mesh(mesh=list(mesh))
    phonon.run_total_dos()
    phonon.write_total_dos(filename=str(work_dir / "total_dos.dat"))
    # Bands: use primitive k-path via pymatgen
    try:
        from pymatgen.symmetry.bandstructure import HighSymmKpath
        from pymatgen.io.phonopy import get_pmg_structure
        struct = get_pmg_structure(phonon.unitcell)
        kpath = HighSymmKpath(struct)
        paths = kpath.kpath["path"]
        pts = kpath.kpath["kpoints"]
        qpoints, labels, connections = [], [], []
        for segment in paths:
            seg_q = [pts[label] for label in segment]
            qpoints.append(seg_q)
        phonon.run_band_structure(qpoints, with_eigenvectors=False)
        phonon.write_yaml_band_structure(filename=str(work_dir / "band.yaml"))
    except Exception as e:
        print(f"Band path build failed: {e}")
    return {"dos": str(work_dir / "total_dos.dat"), "bands": str(work_dir / "band.yaml")}
