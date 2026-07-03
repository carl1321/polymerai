"""Gaussian route line + link0 section generation.

Pure-string generation — Gaussian input format is simple enough that we do not
need a framework. Parameterized over (method, basis, keywords) to avoid the
45-class explosion of the legacy `gaussian_agent.input_sets`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Link0:
    chk: str | None = None
    mem: str = "16GB"
    nprocshared: int = 8
    oldchk: str | None = None

    def render(self) -> str:
        lines = []
        if self.oldchk:
            lines.append(f"%oldchk={self.oldchk}")
        if self.chk:
            lines.append(f"%chk={self.chk}")
        lines.append(f"%mem={self.mem}")
        lines.append(f"%nprocshared={self.nprocshared}")
        return "\n".join(lines)


@dataclass
class Route:
    """A Gaussian `#` route line.

    keywords: ordered list of Gaussian keywords e.g. ["Opt", "Freq", "SCF=Tight"].
    method and basis are rendered as `method/basis` (omit basis for methods that
    don't take one, e.g. semi-empirical).
    """

    method: str
    basis: str | None = "6-31G(d)"
    keywords: list[str] = field(default_factory=list)
    print_level: str = "N"  # P=verbose, N=normal, T=terse

    def render(self) -> str:
        mb = f"{self.method}/{self.basis}" if self.basis else self.method
        parts = [f"#{self.print_level}", mb, *self.keywords]
        return " ".join(parts)


def make_input(
    *,
    route: Route,
    link0: Link0,
    title: str,
    charge: int,
    multiplicity: int,
    geometry: str,
    tail: str = "",
) -> str:
    """Assemble a complete `.gjf` input string.

    geometry: multi-line string, one atom per line ("El x y z").
    tail: extra sections (ModRedundant, basis-set blocks, Link1, …) with leading blank line.
    """
    chunks = [
        link0.render(),
        route.render(),
        "",
        title,
        "",
        f"{charge} {multiplicity}",
        geometry.rstrip(),
        "",
    ]
    body = "\n".join(chunks)
    if tail:
        body = body + tail.rstrip() + "\n"
    return body + "\n"


def geometry_from_ase(atoms) -> str:
    """Convert an ASE Atoms object to a Gaussian coordinate block."""
    lines = []
    for sym, pos in zip(atoms.get_chemical_symbols(), atoms.get_positions()):
        lines.append(f"{sym:<3s} {pos[0]:14.8f} {pos[1]:14.8f} {pos[2]:14.8f}")
    return "\n".join(lines)
