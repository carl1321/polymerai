#!/usr/bin/env python3
"""Step 2: RDKit monomer sanitize → explicit H → 3D embed → MMFF or UFF."""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

from common import load_manifest, save_manifest

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem
except ImportError as e:
    raise SystemExit(
        "RDKit is required for polymer-build step02. Install with: pip install rdkit\n"
        f"Import error: {e}"
    ) from e


def embed_with_retries(mol: Chem.Mol, seed: int, max_retries: int, force_field: str) -> Chem.Mol:
    rng = random.Random(seed)
    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    for attempt in range(max_retries):
        params.randomSeed = seed + attempt * 9973 + rng.randint(0, 10_000)
        hid = AllChem.EmbedMolecule(mol, params)
        if hid < 0:
            continue
        if force_field.upper() in ("MMFF", "MMFF94"):
            try:
                AllChem.MMFFOptimizeMolecule(mol, maxIters=500)
            except ValueError:
                AllChem.UFFOptimizeMolecule(mol, maxIters=500)
        else:
            AllChem.UFFOptimizeMolecule(mol, maxIters=500)
        return mol
    raise RuntimeError(
        f"RDKit EmbedMolecule failed after {max_retries} attempts (seed={seed}). "
        "Try a different --seed or simplify the monomer SMILES."
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="polymer-build step02: RDKit monomer 3D")
    ap.add_argument("--work-dir", type=Path, required=True)
    ap.add_argument("--smiles", type=str, default="", help="Monomer SMILES (if empty, read manifest step01_smiles)")
    ap.add_argument("--force-field", choices=("MMFF", "UFF"), default="MMFF")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--max-retries", type=int, default=12)
    args = ap.parse_args()
    work_dir: Path = args.work_dir
    work_dir.mkdir(parents=True, exist_ok=True)

    smiles = args.smiles.strip()
    if not smiles:
        m = load_manifest(work_dir)
        smiles = str(m.get("step01_smiles", "")).strip()
    if not smiles:
        print("step02: missing --smiles and manifest step01_smiles", file=sys.stderr)
        return 2

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        print(f"step02: MolFromSmiles failed for {smiles!r}", file=sys.stderr)
        return 2
    mol = Chem.AddHs(mol)
    Chem.SanitizeMol(mol)
    mol = embed_with_retries(mol, args.seed, args.max_retries, args.force_field)

    out_sdf = work_dir / "monomer.sdf"
    w = Chem.SDWriter(str(out_sdf))
    w.write(mol)
    w.close()

    save_manifest(
        work_dir,
        {
            "step01_smiles": smiles,
            "step02_monomer_sdf": str(out_sdf.resolve()),
            "step02_force_field": args.force_field,
            "step02_seed": args.seed,
        },
    )
    print(f"wrote {out_sdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
