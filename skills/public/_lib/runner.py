"""Shared retry-loop driver for gaussian-* skills.

Each skill's `scripts/run.py` should:
    1. Parse its own CLI flags.
    2. Build a Route + Link0 + geometry + (charge, mult, title).
    3. Call `run_with_retries(...)` and exit on its return code.

This keeps all 10 skills' run.py files thin and ensures the retry/handler
semantics stay consistent. Step 4 of PLAN.md will add more handlers; this
driver does not need to change.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .executor import LocalExecutor
from .handlers import diagnose
from .inputs import Link0, Route, apply_fix, make_input, pick_geometry
from .parsing import parse_log


def _write_attempt(
    work_dir: Path,
    *,
    route: Route,
    link0: Link0,
    title: str,
    charge: int,
    mult: int,
    geometry: str,
    tail: str = "",
) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    gjf_path = work_dir / "input.gjf"
    gjf_path.write_text(
        make_input(
            route=route,
            link0=link0,
            title=title,
            charge=charge,
            multiplicity=mult,
            geometry=geometry,
            tail=tail,
        ),
        encoding="utf-8",
    )
    return gjf_path


def run_with_retries(
    *,
    route: Route,
    link0: Link0,
    title: str,
    charge: int,
    mult: int,
    geometry: str,
    work_dir: Path,
    tail: str = "",
    max_retries: int = 3,
    dry_run: bool = False,
    executor: Any = None,
    extra_summary: dict | None = None,
) -> tuple[int, dict]:
    """Run a Gaussian job with the standard handler-driven retry loop.

    Returns (exit_code, summary_dict). Summary is also written to
    `work_dir/summary.json`.
    """
    work_dir = Path(work_dir)
    original_geometry = geometry

    if dry_run:
        attempt_dir = work_dir / "attempt_0"
        gjf_path = _write_attempt(
            attempt_dir, route=route, link0=link0, title=title,
            charge=charge, mult=mult, geometry=geometry, tail=tail,
        )
        summary = {
            "dry_run": True,
            "gjf": str(gjf_path),
            "route": route.render(),
            **(extra_summary or {}),
        }
        work_dir.mkdir(parents=True, exist_ok=True)
        (work_dir / "summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        print(f"[dry-run] wrote {gjf_path}", flush=True)
        return 0, summary

    history: list[dict] = []
    parsed: dict = {}
    last_log: Path | None = None
    own_executor = executor is None

    if own_executor:
        executor = LocalExecutor()
        executor.__enter__()

    try:
        for attempt in range(max_retries + 1):
            attempt_dir = work_dir / f"attempt_{attempt}"
            gjf_path = _write_attempt(
                attempt_dir, route=route, link0=link0, title=title,
                charge=charge, mult=mult, geometry=geometry, tail=tail,
            )
            print(f"[attempt {attempt}] wrote {gjf_path}", flush=True)

            result = executor.run(gjf_path, work_dir=attempt_dir)
            last_log = result.log_path
            parsed = parse_log(last_log)
            success = parsed.get("normal_termination") and result.returncode == 0

            history.append({
                "attempt": attempt,
                "returncode": result.returncode,
                "normal_termination": parsed.get("normal_termination"),
                "final_energy": parsed.get("final_energy"),
                "route": route.render(),
            })

            if success:
                break
            if attempt == max_retries:
                history[-1]["gave_up"] = True
                break

            diag = diagnose(last_log)
            if diag is None:
                history[-1]["gave_up"] = "no handler matched"
                break

            handler, fix = diag
            history[-1]["handler"] = handler.name
            history[-1]["fix"] = asdict(fix)
            print(f"[attempt {attempt}] {handler.name} -> {fix.description}", flush=True)

            route, link0 = apply_fix(route, link0, fix)
            geometry = pick_geometry(fix, original_geometry, last_log)
    finally:
        if own_executor:
            executor.__exit__(None, None, None)

    success = bool(history and history[-1].get("normal_termination")
                   and history[-1].get("returncode") == 0)
    summary = {
        "success": success,
        "attempts": history,
        "final_energy": history[-1].get("final_energy") if history else None,
        "frequencies": parsed.get("frequencies"),
        "thermochemistry": parsed.get("thermochemistry"),
        **(extra_summary or {}),
    }
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    return (0 if success else 1), summary
