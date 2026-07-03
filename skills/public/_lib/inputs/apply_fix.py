"""Apply a handler-proposed Fix to produce the next attempt's input.

Lives in `_lib/inputs/` so every gaussian-* skill consumes the same retry
semantics. Pure-data: takes the previous Route/Link0 + Fix and returns the
mutated Route/Link0. Geometry substitution is the caller's job (they own ASE
import); we just expose `pick_geometry` to centralize the policy.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from .route import Link0, Route


def apply_fix(route: Route, link0: Link0, fix) -> tuple[Route, Link0]:
    """Return new (Route, Link0) with the Fix applied. Inputs are not mutated."""
    new_route = deepcopy(route)
    new_link0 = deepcopy(link0)

    if fix.drop_keywords:
        drop = set(fix.drop_keywords)
        new_route.keywords = [k for k in new_route.keywords if k not in drop]

    if fix.new_keywords:
        for kw in fix.new_keywords:
            if kw not in new_route.keywords:
                new_route.keywords.append(kw)

    if fix.link0_patch:
        for k, v in fix.link0_patch.items():
            if not hasattr(new_link0, k):
                raise ValueError(f"Link0 has no attribute '{k}'")
            setattr(new_link0, k, v)

    return new_route, new_link0


def pick_geometry(fix, original_geometry: str, last_log: Path | None) -> str:
    """Return the geometry block for the next attempt.

    If `fix.use_last_geometry` is set and a parsable log exists, extract the
    last geometry from it; otherwise fall back to `original_geometry`.
    """
    if not fix.use_last_geometry or last_log is None:
        return original_geometry

    from ..parsing import parse_log
    parsed = parse_log(last_log)
    coords = parsed.get("geometries")
    atoms = parsed.get("atoms") or []
    if coords is None or len(atoms) == 0:
        return original_geometry

    try:
        last_step = coords[-1]
    except (TypeError, IndexError):
        return original_geometry

    from ase.data import chemical_symbols
    lines = []
    for z, xyz in zip(atoms, last_step):
        sym = chemical_symbols[int(z)]
        lines.append(f"{sym:<3s} {xyz[0]:14.8f} {xyz[1]:14.8f} {xyz[2]:14.8f}")
    return "\n".join(lines)
