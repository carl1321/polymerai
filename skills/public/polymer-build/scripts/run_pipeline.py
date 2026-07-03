#!/usr/bin/env python3
"""PolymerBuild one-shot pipeline: Step1 manifest → Step2–5 + viz (Packmol + pysoftk external)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from common import load_manifest, manifest_path, save_manifest, skill_dir


def run_step(label: str, argv: list[str]) -> None:
    print(f"[polymer-build] {label}: {' '.join(argv)}")
    proc = subprocess.run(argv, capture_output=False)
    if proc.returncode != 0:
        raise RuntimeError(f"{label} failed with exit code {proc.returncode}")


def main() -> int:
    ap = argparse.ArgumentParser(description="PolymerBuild — NL-provided SMILES → pack → export")
    ap.add_argument("--work-dir", type=Path, required=True)
    ap.add_argument("--prompt", type=str, default="", help="Recorded for manifest only; Step1 is LLM in chat")
    ap.add_argument("--smiles", type=str, required=True, help="Monomer SMILES (after Step1 in conversation)")
    ap.add_argument("--placeholder", type=str, default="Br")
    ap.add_argument("--n-copies", type=int, default=6)
    ap.add_argument("--shift", type=float, default=1.25)
    ap.add_argument("--n-chains", type=int, default=4)
    ap.add_argument("--box", type=float, nargs=3, default=(40.0, 40.0, 40.0))
    ap.add_argument("--seed-rdkit", type=int, default=42)
    ap.add_argument("--seed-packmol", type=int, default=12345)
    ap.add_argument("--packmol-binary", type=str, default=None)
    ap.add_argument("--skip-packmol", action="store_true", help="Stop after step03 (no packing/export)")
    ap.add_argument("--extra-pdb", action="append", default=[], metavar="PATHxCOUNT")
    args = ap.parse_args()

    work_dir: Path = args.work_dir
    work_dir.mkdir(parents=True, exist_ok=True)
    scripts = Path(__file__).resolve().parent
    py = sys.executable

    save_manifest(
        work_dir,
        {
            "step01_smiles": args.smiles.strip(),
            "step01_prompt": args.prompt.strip(),
            "pipeline": "polymer-build",
        },
    )

    run_step(
        "step02_rdkit",
        [
            py,
            str(scripts / "step02_rdkit.py"),
            "--work-dir",
            str(work_dir),
            "--smiles",
            args.smiles.strip(),
            "--seed",
            str(args.seed_rdkit),
        ],
    )

    run_step(
        "step03_pysoftk",
        [
            py,
            str(scripts / "step03_pysoftk.py"),
            "--work-dir",
            str(work_dir),
            "--placeholder",
            args.placeholder,
            "--n-copies",
            str(args.n_copies),
            "--shift",
            str(args.shift),
        ],
    )

    if args.skip_packmol:
        print(json.dumps({"ok": True, "stopped_after": "step03", "manifest": str(manifest_path(work_dir))}, indent=2))
        return 0

    cmd4 = [
        py,
        str(scripts / "step04_packmol.py"),
        "--work-dir",
        str(work_dir),
        "--n-chains",
        str(args.n_chains),
        "--box",
        str(args.box[0]),
        str(args.box[1]),
        str(args.box[2]),
        "--seed",
        str(args.seed_packmol),
    ]
    if args.packmol_binary:
        cmd4.extend(["--packmol-binary", args.packmol_binary])
    for x in args.extra_pdb:
        cmd4.extend(["--extra-pdb", x])
    run_step("step04_packmol", cmd4)

    run_step(
        "step05_export",
        [py, str(scripts / "step05_export.py"), "--work-dir", str(work_dir)],
    )

    run_step(
        "viz_html",
        [py, str(scripts / "viz_html.py"), "--work-dir", str(work_dir)],
    )

    man = load_manifest(work_dir)
    print(json.dumps({"ok": True, "skill": str(skill_dir()), "manifest": man}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1)
