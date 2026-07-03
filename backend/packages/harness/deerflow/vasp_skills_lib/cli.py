"""CLI entry for poll_command examples (skills implement real domain logic in sandbox)."""

from __future__ import annotations

import argparse
import json
import sys


def cmd_poll(args: argparse.Namespace) -> int:
    """Emit one-line JSON for gateway dispatcher — placeholder until wired to real calc_runtime."""
    payload = {
        "status": args.phase or "running",
        "message": "vasp_skills_lib poll stub: implement skill-specific checks under sandbox paths",
    }
    if args.external_ref:
        payload["external_ref"] = args.external_ref
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="deerflow.vasp_skills_lib.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_poll = sub.add_parser("poll", help="Emit poll status JSON (last line consumed by gateway)")
    p_poll.add_argument("--external-ref", default="", help="Echo external job id into JSON")
    p_poll.add_argument(
        "--phase",
        default="running",
        help="status field for mapping (running|completed|failed|cancelled|timeout)",
    )
    p_poll.set_defaults(func=cmd_poll)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
