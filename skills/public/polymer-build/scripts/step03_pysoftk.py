#!/usr/bin/env python3
"""Step 3: linear polymer (Lp) — bundled ``polysoftk_lite`` + Open Babel (PyBel)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from common import load_manifest, save_manifest

try:
    from rdkit import Chem
except ImportError as e:
    raise SystemExit(f"RDKit required: {e}") from e

try:
    from polysoftk_lite import Lp
except ImportError as e:
    raise SystemExit(
        "polymer-build step03 requires the vendored ``polysoftk_lite`` package next to this skill "
        f"(expected under {_SKILL_ROOT / 'polysoftk_lite'}).\n"
        f"Import error: {e}"
    ) from e


def main() -> int:
    ap = argparse.ArgumentParser(description="polymer-build step03: PySoftK Lp polymer")
    ap.add_argument("--work-dir", type=Path, required=True)
    ap.add_argument("--monomer-sdf", type=Path, default=None, help="Default: work_dir/monomer.sdf")
    ap.add_argument("--placeholder", type=str, default="Br", help='Placeholder element symbol, e.g. Br or Pt')
    ap.add_argument("--n-copies", type=int, default=6, help="Number of repeat units (chain length proxy)")
    ap.add_argument("--shift", type=float, default=1.25)
    ap.add_argument("--force-field", choices=("MMFF", "UFF"), default="MMFF")
    ap.add_argument("--relax-iterations", type=int, default=350)
    ap.add_argument("--rot-steps", type=int, default=125)
    args = ap.parse_args()
    work_dir: Path = args.work_dir
    work_dir.mkdir(parents=True, exist_ok=True)

    sdf = args.monomer_sdf or (work_dir / "monomer.sdf")
    if not sdf.is_file():
        print(f"step03: monomer SDF not found: {sdf}", file=sys.stderr)
        return 2

    mol = Chem.MolFromMolFile(str(sdf), sanitize=True, removeHs=False)
    if mol is None:
        print(f"step03: MolFromMolFile failed: {sdf}", file=sys.stderr)
        return 2

    try:
        builder = Lp(mol, args.placeholder, int(args.n_copies), float(args.shift))
        obmol = builder.linear_polymer(
            force_field=args.force_field,
            relax_iterations=int(args.relax_iterations),
            rot_steps=int(args.rot_steps),
            no_att=True,
        )
    except Exception as e:
        print(f"step03: PySoftK Lp.linear_polymer failed: {e}", file=sys.stderr)
        return 3

    out_pdb = work_dir / "polymer_chain.pdb"
    pdb_text = obmol.write("pdb")
    out_pdb.write_text(pdb_text, encoding="utf-8")

    save_manifest(
        work_dir,
        {
            "step03_polymer_pdb": str(out_pdb.resolve()),
            "step03_placeholder": args.placeholder,
            "step03_n_copies": int(args.n_copies),
            "step03_shift": float(args.shift),
        },
    )
    print(f"wrote {out_pdb}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
