"""Single-run summary: total energy, band gap, magmom, lattice, convergence."""
from __future__ import annotations

from pathlib import Path

from ..parser.vasprun import VasprunWrapper


def collect(workdir: str | Path) -> dict:
    """Return a dict of summary fields. Missing fields → None."""
    workdir = Path(workdir)
    vasprun = workdir / "vasprun.xml"
    if not vasprun.is_file():
        return {"workdir": str(workdir), "error": "no vasprun.xml"}

    vw = VasprunWrapper(vasprun)
    s = vw.structure
    a, b, c = s.lattice.abc
    alpha, beta, gamma = s.lattice.angles
    return {
        "workdir": str(workdir),
        "formula": s.composition.reduced_formula,
        "n_atoms": len(s),
        "lattice_abc": (round(a, 4), round(b, 4), round(c, 4)),
        "lattice_angles": (round(alpha, 2), round(beta, 2), round(gamma, 2)),
        "volume": round(s.volume, 3),
        "total_energy_eV": round(vw.total_energy, 6),
        "energy_per_atom": round(vw.total_energy / len(s), 6),
        "band_gap_eV": vw.band_gap,
        "is_metal": vw.is_metal,
        "total_magnetization": vw.magnetization,
        "converged": vw.converged,
        "incar_keys": sorted(vw.incar.keys()),
    }


def to_markdown(summary: dict) -> str:
    """Render the summary dict as a markdown table."""
    if "error" in summary:
        return f"**workdir**: `{summary['workdir']}` — {summary['error']}\n"
    lines = [
        f"# VASP run summary — `{summary['workdir']}`",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| Formula | {summary['formula']} |",
        f"| Atoms | {summary['n_atoms']} |",
        f"| Lattice a,b,c (Å) | {summary['lattice_abc']} |",
        f"| Angles α,β,γ (°) | {summary['lattice_angles']} |",
        f"| Volume (Å³) | {summary['volume']} |",
        f"| Total energy (eV) | {summary['total_energy_eV']} |",
        f"| Energy / atom (eV) | {summary['energy_per_atom']} |",
        f"| Band gap (eV) | {summary['band_gap_eV']} |",
        f"| Metal? | {summary['is_metal']} |",
        f"| Total magnetization (μB) | {summary['total_magnetization']} |",
        f"| SCF + ionic converged | {summary['converged']} |",
        "",
        f"INCAR keys ({len(summary['incar_keys'])}): "
        f"`{', '.join(summary['incar_keys'])}`",
        "",
    ]
    return "\n".join(lines)


def write(workdir: str | Path, out: str | Path | None = None) -> Path:
    workdir = Path(workdir)
    summary = collect(workdir)
    out_path = Path(out) if out else workdir / "summary.md"
    out_path.write_text(to_markdown(summary), encoding="utf-8")
    return out_path
