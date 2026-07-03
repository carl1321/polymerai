#!/usr/bin/env python3
"""vasp-diagnose CLI — read-only post-mortem of a VASP work directory.

Scans vasp.out / OUTCAR / stderr.txt with ExtendedVaspErrorHandler and prints
a JSON report: detected errors, severity, ranked suggested fixes.
No VASP, no scheduler, no network calls.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from vasp_skills_lib.handlers.vasp_errors import (
    ExtendedVaspErrorHandler,
    PATTERNS,
)


def _suggestions_for(error_name: str) -> list[dict]:
    for name, _, severity, corrs in PATTERNS:
        if name == error_name:
            return [
                {
                    "description": c.description,
                    "confidence": c.confidence,
                    "incar_updates": dict(c.incar_updates),
                    "actions": list(c.actions),
                }
                for c in corrs
            ]
    return []


def main() -> int:
    p = argparse.ArgumentParser(prog="vasp-diagnose",
                                description="Post-mortem analysis of a VASP work dir")
    p.add_argument("work_dir", type=Path, help="directory containing OUTCAR/vasp.out")
    p.add_argument("--format", choices=["json", "text"], default="json")
    args = p.parse_args()

    if not args.work_dir.exists():
        print(f"work_dir not found: {args.work_dir}", file=sys.stderr)
        return 1

    h = ExtendedVaspErrorHandler(args.work_dir)
    errors = h.detect()

    report = {
        "work_dir": str(args.work_dir),
        "n_errors": len(errors),
        "errors": [
            {
                "name": e.name,
                "severity": e.severity.value,
                "line": e.line_number,
                "message": e.message.strip(),
                "suggestions": _suggestions_for(e.name),
            }
            for e in errors
        ],
    }

    if args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        if not errors:
            print(f"No VASP errors detected in {args.work_dir}")
        else:
            print(f"Found {len(errors)} error(s) in {args.work_dir}:")
            for e in errors:
                print(f"\n  [{e.severity.value.upper()}] {e.name} (line ~{e.line_number})")
                print(f"    match: {e.message.strip()}")
                for s in _suggestions_for(e.name):
                    updates = ", ".join(f"{k}={v}" for k, v in s["incar_updates"].items())
                    acts = (" + " + ", ".join(s["actions"])) if s["actions"] else ""
                    print(f"    - [{s['confidence']:.0%}] {s['description']}: {updates}{acts}")
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())
