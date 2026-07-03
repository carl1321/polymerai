#!/usr/bin/env python3
"""Smoke test: workflow skill_runner + vasp-relax on SCNet (or --dry-run without credentials).

Usage (from backend/):
  uv run python scripts/test_workflow_skill_scnet.py
  uv run python scripts/test_workflow_skill_scnet.py --submit   # real SCNet submit (needs SCNET_AK/SK)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parent
sys.path.insert(0, str(_BACKEND))

POSCAR = _REPO / "skills/public/vasp-potcar/tests/fixtures/poscar/BN_POSCAR"
VASP_CONFIG = _REPO / "skills/public/_shared-vasp/config.yaml"
POTCAR_ROOT = _REPO / "skills/public/pot5.4/PBE"


def _write_bn_potcar(work_dir: Path) -> None:
    """Concat element POTCARs for BN fixture (avoids pymatgen path quirks in CI)."""
    parts = []
    for el in ("B", "N"):
        p = POTCAR_ROOT / el / "POTCAR"
        if not p.is_file():
            raise FileNotFoundError(p)
        parts.append(p.read_text(encoding="utf-8", errors="replace"))
    (work_dir / "POTCAR").write_text("".join(parts), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--submit", action="store_true", help="Real SCNet submit (default: dry-run only)")
    args = parser.parse_args()

    if not POSCAR.is_file():
        print(f"FAIL: missing fixture POSCAR: {POSCAR}")
        return 1
    if not VASP_CONFIG.is_file():
        print(f"FAIL: missing VASP config: {VASP_CONFIG}")
        return 1

    from extensions._core.workflow.format_skill_output import format_skill_output
    from extensions._core.workflow.skill_runner import run_skill, skill_result_to_tool_json
    from deerflow.runtime.async_tasks.envelope import resolve_submit_envelope

    work_dir = Path(tempfile.mkdtemp(prefix="wf-skill-test-"))
    print(f"work_dir={work_dir}")

    _write_bn_potcar(work_dir)

    argv = [
        str(POSCAR),
        "--work-dir",
        str(work_dir),
        "--config",
        str(VASP_CONFIG),
        "--executor",
        "scnet",
        "--first-poll-delay-seconds",
        "30",
    ]
    if not args.submit:
        argv.append("--dry-run")
        print("MODE: dry-run (inputs only, no SCNet submit)")
    else:
        print("MODE: real SCNet submit (detach envelope expected; uses _shared-vasp profiles.yaml)")

    try:
        result = run_skill("vasp-relax", work_dir=str(work_dir), argv=argv)
    except Exception as e:
        print(f"FAIL: run_skill raised: {e}")
        return 1

    print("run_skill exit_code:", result.get("exit_code"))
    if result.get("stderr"):
        print("stderr tail:", (result["stderr"] or "")[-800:])
    if result.get("stdout"):
        print("stdout tail:", (result["stdout"] or "")[-400:])

    tool_json = skill_result_to_tool_json(result)
    envelope = result.get("async_envelope") or resolve_submit_envelope(tool_json)
    if args.submit:
        if not envelope or envelope.get("status") != "submitted":
            print("FAIL: expected detach envelope status=submitted")
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str)[:2000])
            return 1
        print("OK: detach envelope captured")
        print(json.dumps({k: envelope.get(k) for k in ("status", "task_kind", "external_ref", "poll_interval_seconds")}, ensure_ascii=False))

    formatted = format_skill_output(
        tool_results=[tool_json],
        output_fields=[
            {"name": "success", "type": "boolean"},
            {"name": "work_dir", "type": "string"},
        ],
        work_dir_hint=str(work_dir),
    )
    print("format_skill_output:", json.dumps(formatted, ensure_ascii=False, indent=2)[:1200])

    if args.dry_run if hasattr(args, "dry_run") else not args.submit:
        if result.get("exit_code") != 0:
            print("FAIL: dry-run expected exit 0")
            return 1
        print("OK: dry-run skill_runner path")
        return 0

    out = formatted.get("output") if isinstance(formatted.get("output"), dict) else {}
    if out.get("_awaiting_external") or out.get("status") == "submitted":
        print("OK: format_skill_output marks submitted / awaiting_external")
        return 0
    print("WARN: submit succeeded but output shape unexpected; check result above")
    return 0 if result.get("exit_code") == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
