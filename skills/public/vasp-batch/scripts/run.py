#!/usr/bin/env python3
"""vasp-batch CLI — run the same VASP calc type on N structures with failure isolation.

Architecture:
    Unlike vasp-phonon / vasp-elastic / vasp-defect, vasp-batch dispatches to
    sub-skill CLIs (vasp-relax/scripts/run.py, ...) via subprocess. Each
    sub-skill internally runs JobScheduler against ONE work_dir. So vasp-batch
    sits one layer above and uses ThreadPoolExecutor over those subprocesses.

    For very large batches (N > 20) on a single SCNet token, consider
    --parallel 4-8 to bound concurrent token usage.

Resume:
    --resume skips structures whose summary.json reports success=True.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import subprocess
import sys
from pathlib import Path

SKILL_MAP = {
    "relax": "vasp-relax",
    "scf": "vasp-scf",
    "band": "vasp-band",
    "dos": "vasp-dos",
    "dielectric": "vasp-dielectric",
    "optics": "vasp-optics",
    "magnetic": "vasp-magnetic",
}


def _skill_script(skill_root: Path, calc: str) -> Path:
    return skill_root / SKILL_MAP[calc] / "scripts" / "run.py"


def _already_done(work_dir: Path) -> bool:
    s = work_dir / "summary.json"
    if not s.exists():
        return False
    try:
        data = json.loads(s.read_text(encoding="utf-8"))
    except Exception:
        return False
    if data.get("submitted") is True:
        return False
    return bool(data.get("success"))


def _one(poscar: Path, work_dir: Path, script: Path, extra: list[str]) -> dict:
    cmd = [sys.executable, str(script), str(poscar), "--work-dir", str(work_dir)] + extra
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=None)
        return {
            "poscar": str(poscar),
            "work_dir": str(work_dir),
            "returncode": proc.returncode,
            "success": proc.returncode == 0,
            "stdout_tail": proc.stdout[-2000:],
            "stderr_tail": proc.stderr[-2000:],
        }
    except Exception as e:
        return {"poscar": str(poscar), "work_dir": str(work_dir),
                "returncode": -1, "success": False, "error": str(e)}


def main() -> int:
    p = argparse.ArgumentParser(prog="vasp-batch")
    p.add_argument("poscars", nargs="+", type=Path,
                   help="POSCAR files or glob-expanded list")
    p.add_argument("--calc", choices=list(SKILL_MAP), required=True)
    p.add_argument("--work-dir", type=Path, default=Path("./batch"))
    p.add_argument("--parallel", type=int, default=1,
                   help="max concurrent jobs (SSH-backed executors can submit in parallel)")
    p.add_argument("--no-resume", dest="resume", action="store_false",
                   help="不跳过 work_dir/summary.json 已成功的结构 (默认会跳过)")
    p.set_defaults(resume=True)
    p.add_argument("--skill-root", type=Path, default=Path(__file__).resolve().parent.parent.parent,
                   help="parent dir containing vasp-relax/ vasp-scf/ etc.")
    # Extra args forwarded to the sub-skill (use `--` separator, argparse REMAINDER)
    p.add_argument("extra", nargs=argparse.REMAINDER,
                   help="pass-through args for the sub-skill after `--`")
    args = p.parse_args()

    script = _skill_script(args.skill_root, args.calc)
    if not script.exists():
        print(f"Sub-skill script not found: {script}", file=sys.stderr)
        return 1

    args.work_dir.mkdir(parents=True, exist_ok=True)
    extra = [x for x in args.extra if x != "--"]

    jobs: list[tuple[Path, Path]] = []
    skipped: list[Path] = []
    for pos in args.poscars:
        name = pos.stem
        wd = args.work_dir / name
        if args.resume and _already_done(wd):
            skipped.append(wd)
            continue
        jobs.append((pos, wd))
    if skipped:
        print(f"  resume: skipping {len(skipped)} already-successful structures")

    results: list[dict] = []
    if args.parallel <= 1:
        for pos, wd in jobs:
            print(f"  [{wd.name}] running...")
            results.append(_one(pos, wd, script, extra))
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as ex:
            futures = {ex.submit(_one, pos, wd, script, extra): wd.name for pos, wd in jobs}
            for f in concurrent.futures.as_completed(futures):
                r = f.result()
                print(f"  [{futures[f]}] {'ok' if r['success'] else 'FAIL'}")
                results.append(r)

    # Write summary
    summary_path = args.work_dir / "summary.json"
    summary_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    csv_path = args.work_dir / "summary.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["poscar", "work_dir", "success", "returncode"])
        for r in results:
            w.writerow([r["poscar"], r["work_dir"], r["success"], r.get("returncode", -1)])

    n_ok = sum(1 for r in results if r["success"])
    print(f"\nBatch done: {n_ok}/{len(results)} succeeded. Summary: {csv_path}")
    return 0 if n_ok == len(results) else 2


if __name__ == "__main__":
    sys.exit(main())
