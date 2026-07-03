"""Multi-workdir comparison table (PBE vs HSE vs SCAN, etc.)."""
from __future__ import annotations

from pathlib import Path

from .summary import collect


_FIELDS = [
    ("formula", "Formula"),
    ("n_atoms", "Atoms"),
    ("volume", "Volume (Å³)"),
    ("total_energy_eV", "E_total (eV)"),
    ("energy_per_atom", "E/atom (eV)"),
    ("band_gap_eV", "Gap (eV)"),
    ("is_metal", "Metal?"),
    ("total_magnetization", "M_tot (μB)"),
    ("converged", "Converged?"),
]


def to_markdown(rows: list[dict]) -> str:
    header = "| " + " | ".join(["Workdir"] + [label for _, label in _FIELDS]) + " |"
    sep = "| " + " | ".join(["---"] * (1 + len(_FIELDS))) + " |"
    body = []
    for r in rows:
        if "error" in r:
            body.append(f"| `{r['workdir']}` | _{r['error']}_ " + "|" * len(_FIELDS))
            continue
        cells = [f"`{r['workdir']}`"] + [str(r.get(k, "")) for k, _ in _FIELDS]
        body.append("| " + " | ".join(cells) + " |")
    return "\n".join(["# VASP run comparison", "", header, sep, *body, ""])


def write(dirs: list[Path], out: str | Path | None = None) -> Path:
    rows = [collect(d) for d in dirs]
    md = to_markdown(rows)
    base = Path(dirs[0]).parent
    out_path = Path(out) if out else base / "compare.md"
    out_path.write_text(md, encoding="utf-8")
    return out_path
