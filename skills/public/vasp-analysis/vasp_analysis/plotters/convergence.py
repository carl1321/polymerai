"""Convergence test plot: scan a list of dirs for one INCAR parameter vs total energy."""
from __future__ import annotations

from pathlib import Path

from .base import apply_style, resolve_output


def _read_param(workdir: Path, param: str) -> float | None:
    incar = workdir / "INCAR"
    kpoints = workdir / "KPOINTS"
    if param == "ENCUT" and incar.is_file():
        for line in incar.read_text(errors="ignore").splitlines():
            s = line.split("#", 1)[0].strip().upper()
            if s.startswith("ENCUT"):
                try:
                    return float(s.split("=", 1)[1].strip().split()[0])
                except (IndexError, ValueError):
                    return None
    if param == "SIGMA" and incar.is_file():
        for line in incar.read_text(errors="ignore").splitlines():
            s = line.split("#", 1)[0].strip().upper()
            if s.startswith("SIGMA"):
                try:
                    return float(s.split("=", 1)[1].strip().split()[0])
                except (IndexError, ValueError):
                    return None
    if param == "KPOINTS" and kpoints.is_file():
        try:
            mesh_line = kpoints.read_text(errors="ignore").splitlines()[3]
            nums = [int(x) for x in mesh_line.split()[:3]]
            return float(nums[0] * nums[1] * nums[2])
        except (IndexError, ValueError):
            return None
    return None


def _read_energy(workdir: Path) -> float | None:
    from pymatgen.io.vasp import Vasprun

    v = workdir / "vasprun.xml"
    if not v.is_file():
        return None
    try:
        return float(Vasprun(str(v)).final_energy)
    except Exception:
        return None


def plot(
    dirs: list[Path],
    *,
    param: str,
    out: str | Path | None = None,
    fmt: str = "png",
) -> Path:
    import matplotlib.pyplot as plt

    apply_style()
    rows: list[tuple[float, float, str]] = []
    for d in dirs:
        d = Path(d)
        x = _read_param(d, param)
        y = _read_energy(d)
        if x is not None and y is not None:
            rows.append((x, y, d.name))
    rows.sort(key=lambda r: r[0])
    if not rows:
        raise ValueError("No (param, energy) pairs collected — check inputs")

    xs = [r[0] for r in rows]
    ys = [r[1] for r in rows]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(xs, ys, "o-")
    e_ref = ys[-1]
    ax2 = ax.twinx()
    ax2.plot(xs, [(y - e_ref) * 1000 for y in ys], "s--", color="tab:orange")
    ax.set_xlabel(param)
    ax.set_ylabel("Total energy (eV)")
    ax2.set_ylabel("ΔE vs largest (meV)", color="tab:orange")
    ax.set_title(f"Convergence of {param}")

    base = Path(dirs[0]).parent
    out_path = Path(out) if out else resolve_output(base, f"convergence_{param}", fmt)
    fig.savefig(out_path)
    plt.close(fig)
    return out_path
