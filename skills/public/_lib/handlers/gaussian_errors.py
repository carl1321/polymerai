"""Gaussian error-pattern handlers.

**Step-2 seed.** Three handlers ported from the legacy
`gaussian_agent.handlers.gaussian_error` (SCF non-convergence, OPT not
converged, OPT max-cycles) so the retry loop in `gaussian-opt/scripts/run.py`
has something real to dispatch on. The full 25+ port lands in Step 4 of
PLAN.md — add new handlers here as `BaseHandler` subclasses and append to
`HANDLERS` (order = priority; first match wins).

Reference (rewrite, do not import):
    D:/code/gaussian-agent/gaussian_agent/handlers/gaussian_error.py
"""

from __future__ import annotations

import re
from pathlib import Path

from .base import BaseHandler, Fix


def _read_tail(log_path: Path, max_bytes: int = 200_000) -> str:
    """Read the tail of a log file (Gaussian errors land near the end)."""
    p = Path(log_path)
    size = p.stat().st_size
    with p.open("rb") as f:
        if size > max_bytes:
            f.seek(size - max_bytes)
        return f.read().decode("utf-8", errors="replace")


class SCFNotConverged(BaseHandler):
    name = "scf_not_converged"
    _patterns = (
        re.compile(r"Convergence criterion not met", re.IGNORECASE),
        re.compile(r"SCF has not converged", re.IGNORECASE),
    )

    def detect(self, log_text: str) -> bool:
        return any(p.search(log_text) for p in self._patterns)

    def propose_fix(self, log_path: Path) -> Fix:
        return Fix(
            description="SCF did not converge — increase MaxCycle and use quadratic convergence (XQC)",
            new_keywords=["SCF=(MaxCycle=200,XQC)"],
            use_last_geometry=True,
        )


class OptNotConverged(BaseHandler):
    name = "opt_not_converged"
    _patterns = (
        re.compile(r"Optimization stopped", re.IGNORECASE),
    )

    def detect(self, log_text: str) -> bool:
        return any(p.search(log_text) for p in self._patterns)

    def propose_fix(self, log_path: Path) -> Fix:
        return Fix(
            description="Geometry optimization stopped — restart with CalcFC and more cycles",
            new_keywords=["Opt=(MaxCycles=200,CalcFC)"],
            use_last_geometry=True,
        )


class OptMaxCycles(BaseHandler):
    name = "opt_maxcycles"
    _pattern = re.compile(r"Number of steps exceeded", re.IGNORECASE)

    def detect(self, log_text: str) -> bool:
        return bool(self._pattern.search(log_text))

    def propose_fix(self, log_path: Path) -> Fix:
        return Fix(
            description="Optimization exceeded MaxCycles — bump and restart from last geometry",
            new_keywords=["Opt=(MaxCycles=300)"],
            use_last_geometry=True,
        )


HANDLERS: list[BaseHandler] = [
    SCFNotConverged(),
    OptNotConverged(),
    OptMaxCycles(),
]


def diagnose(log_path: str | Path) -> tuple[BaseHandler, Fix] | None:
    """Run all handlers against the log; return the first match's (handler, fix)."""
    log_text = _read_tail(Path(log_path))
    for h in HANDLERS:
        if h.detect(log_text):
            return h, h.propose_fix(Path(log_path))
    return None
