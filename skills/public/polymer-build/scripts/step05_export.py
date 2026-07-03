#!/usr/bin/env python3
"""Step 5: LAMMPS data + input skeleton; VASP POSCAR + INCAR + KPOINTS; POTCAR how-to."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import default_outputs_dir, load_manifest, repo_skills_public, save_manifest, skill_dir

try:
    from rdkit import Chem
except ImportError as e:
    raise SystemExit(f"RDKit required for polymer-build step05 PDB parsing: {e}") from e

try:
    from pymatgen.core import Lattice, Structure
    from pymatgen.io.lammps.data import LammpsData
    from pymatgen.io.vasp.inputs import Incar, Poscar
except ImportError as e:
    raise SystemExit(
        "pymatgen is required for polymer-build step05. Install with: pip install pymatgen\n"
        f"Import error: {e}"
    ) from e


LAMMPS_IN_SKEL = """# Minimal skeleton — pair/bonded styles MUST be set for your chemistry.
units           real
atom_style      atomic
boundary        p p p

read_data       data.lammps

# Example only (Lennard-Jones placeholders — replace with a real force field):
# pair_style      lj/cut 12.0
# pair_coeff      1 1 0.11 3.5

neighbor        2.0 bin
timestep        1.0

thermo          100
run             0
"""


def pdb_to_structure(pdb_path: Path, box_abc: tuple[float, float, float]) -> Structure:
    mol = Chem.MolFromPDBFile(str(pdb_path), removeHs=False, sanitize=False)
    if mol is None:
        raise ValueError(f"RDKit could not parse PDB: {pdb_path}")
    try:
        Chem.SanitizeMol(mol)
    except Exception:
        pass
    if mol.GetNumConformers() < 1:
        raise ValueError(f"PDB has no coordinates: {pdb_path}")
    conf = mol.GetConformer()
    coords = conf.GetPositions()
    species = [mol.GetAtomWithIdx(i).GetSymbol() for i in range(mol.GetNumAtoms())]
    lat = Lattice.orthorhombic(box_abc[0], box_abc[1], box_abc[2])
    return Structure(lat, species, coords, coords_are_cartesian=True)


def write_potcar_howto(dest: Path) -> None:
    pub = repo_skills_public()
    vasp_potcar = pub / "vasp-potcar"
    lines = [
        "POTCAR is not auto-generated here (element pseudo-potential mapping belongs in vasp-potcar).",
        "",
        "Recommended:",
        f"1. Use the `vasp-potcar` skill / CLI next to this repo: {vasp_potcar}",
        "2. Point its POTCAR library path per that skill's SKILL.md and generate POTCAR for POSCAR.",
        "",
        "After step05 you should have POSCAR in this work directory; feed it to vasp-potcar.",
        "",
        f"Relative skill path from polymer-build: ../../vasp-potcar (under skills/public/).",
    ]
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="polymer-build step05: LAMMPS + VASP export")
    ap.add_argument("--work-dir", type=Path, required=True)
    ap.add_argument("--packed-pdb", type=Path, default=None)
    args = ap.parse_args()
    work_dir: Path = args.work_dir
    work_dir.mkdir(parents=True, exist_ok=True)

    man = load_manifest(work_dir)
    pdb_path = args.packed_pdb or Path(man.get("step04_packed_pdb", work_dir / "packed.pdb"))
    if not pdb_path.is_file():
        pdb_path = work_dir / "packed.pdb"
    if not pdb_path.is_file():
        print(f"step05: packed PDB not found: {pdb_path}", file=sys.stderr)
        return 2

    box = man.get("step04_box")
    if not box or len(box) != 3:
        box = [40.0, 40.0, 40.0]
    box_t = (float(box[0]), float(box[1]), float(box[2]))

    struct = pdb_to_structure(pdb_path, box_t)

    data_out = work_dir / "data.lammps"
    lmp = LammpsData.from_structure(struct, atom_style="atomic")
    lmp.write_file(str(data_out))

    in_path = work_dir / "in.lammps"
    in_path.write_text(LAMMPS_IN_SKEL, encoding="utf-8")

    top_notes = work_dir / "topology_notes.md"
    top_notes.write_text(
        "## Topology note\n\n"
        "`data.lammps` is exported with `atom_style atomic` (coordinates + types only). "
        "Bonded force fields for polymers require `full`/`molecular` styles plus bonds/angles/dihedrals "
        "(e.g. via specialized builders or MDAnalysis/ff assignment). "
        "Use this as a geometry-packed starting point; refine the FF topology separately.\n",
        encoding="utf-8",
    )

    poscar_path = work_dir / "POSCAR"
    Poscar(struct).write_file(str(poscar_path))

    incar = Incar(
        {
            "ENCUT": 520,
            "EDIFF": 1e-4,
            "IBRION": 2,
            "ISIF": 3,
            "NSW": 200,
            "ISMEAR": 0,
            "SIGMA": 0.05,
            "LWAVE": False,
            "LCHARG": False,
        }
    )
    incar_path = work_dir / "INCAR"
    incar.write_file(str(incar_path))

    kpath = work_dir / "KPOINTS"
    kpath.write_text(
        "KPOINTS — polymer-build template (refine k-mesh for your lattice)\n"
        "0\n"
        "Gamma\n"
        "1 1 1\n"
        "0 0 0\n",
        encoding="utf-8",
    )

    howto = work_dir / "POTCAR.howto.txt"
    write_potcar_howto(howto)

    outs = default_outputs_dir(work_dir)
    summary = outs / "polymer_build_export_summary.txt"
    summary.write_text(
        f"work_dir: {work_dir.resolve()}\n"
        f"packed_pdb: {pdb_path.resolve()}\n"
        f"box (Å): {box_t}\n"
        f"LAMMPS data: {data_out.resolve()}\n"
        f"LAMMPS input skeleton: {in_path.resolve()}\n"
        f"VASP POSCAR: {poscar_path.resolve()}\n"
        f"POTCAR instructions: {howto.resolve()}\n"
        f"polymer-build skill: {skill_dir()}\n",
        encoding="utf-8",
    )

    save_manifest(
        work_dir,
        {
            "step05_data_lammps": str(data_out.resolve()),
            "step05_in_lammps": str(in_path.resolve()),
            "step05_poscar": str(poscar_path.resolve()),
            "step05_summary": str(summary.resolve()),
        },
    )
    print(f"wrote {data_out}, {in_path}, {poscar_path}, {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
