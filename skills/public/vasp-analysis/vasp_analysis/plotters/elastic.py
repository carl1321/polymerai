"""Elastic constants: 6x6 heatmap + Voigt/Reuss/Hill table.

Reads OUTCAR (TOTAL ELASTIC MODULI block) and produces a heatmap + a sidecar
``elastic_summary.md`` next to the figure.
"""
from __future__ import annotations

from pathlib import Path

from ..parser.outcar import OutcarWrapper
from .base import apply_style, resolve_output


_LABELS = ["xx", "yy", "zz", "yz", "xz", "xy"]


def _voigt_reuss_hill(c: "np.ndarray") -> dict[str, float]:
    import numpy as np

    s = np.linalg.inv(c)
    Kv = (c[0, 0] + c[1, 1] + c[2, 2] + 2 * (c[0, 1] + c[1, 2] + c[0, 2])) / 9.0
    Gv = ((c[0, 0] + c[1, 1] + c[2, 2]) - (c[0, 1] + c[1, 2] + c[0, 2])
          + 3 * (c[3, 3] + c[4, 4] + c[5, 5])) / 15.0
    Kr = 1.0 / (s[0, 0] + s[1, 1] + s[2, 2] + 2 * (s[0, 1] + s[1, 2] + s[0, 2]))
    Gr = 15.0 / (4 * (s[0, 0] + s[1, 1] + s[2, 2])
                 - 4 * (s[0, 1] + s[1, 2] + s[0, 2])
                 + 3 * (s[3, 3] + s[4, 4] + s[5, 5]))
    Kh = (Kv + Kr) / 2.0
    Gh = (Gv + Gr) / 2.0
    Eh = (9 * Kh * Gh) / (3 * Kh + Gh) if (3 * Kh + Gh) != 0 else float("nan")
    nu = (3 * Kh - 2 * Gh) / (2 * (3 * Kh + Gh)) if (3 * Kh + Gh) != 0 else float("nan")
    return {"Kv": Kv, "Gv": Gv, "Kr": Kr, "Gr": Gr, "Kh": Kh, "Gh": Gh,
            "E_Hill": Eh, "nu_Hill": nu}


def plot(
    workdir: str | Path,
    *,
    out: str | Path | None = None,
    fmt: str = "png",
) -> Path:
    import matplotlib.pyplot as plt
    import numpy as np

    workdir = Path(workdir)
    apply_style()
    outcar = OutcarWrapper(workdir / "OUTCAR")
    c = outcar.elastic_tensor  # 6x6 GPa

    out_path = Path(out) if out else resolve_output(workdir, "elastic", fmt)

    fig, ax = plt.subplots(figsize=(5, 4.5))
    im = ax.imshow(c, cmap="RdBu_r", vmin=-np.max(np.abs(c)), vmax=np.max(np.abs(c)))
    ax.set_xticks(range(6))
    ax.set_yticks(range(6))
    ax.set_xticklabels(_LABELS)
    ax.set_yticklabels(_LABELS)
    ax.set_title("Elastic stiffness $C_{ij}$ (GPa)")
    for i in range(6):
        for j in range(6):
            ax.text(j, i, f"{c[i, j]:.0f}", ha="center", va="center",
                    color="black", fontsize=8)
    fig.colorbar(im, ax=ax, fraction=0.045)
    fig.savefig(out_path)
    plt.close(fig)

    summary = _voigt_reuss_hill(c)
    md = workdir / "elastic_summary.md"
    md.write_text(
        "# Elastic moduli (GPa)\n\n"
        "| Quantity | Voigt | Reuss | Hill |\n"
        "|----------|-------|-------|------|\n"
        f"| Bulk K   | {summary['Kv']:.1f} | {summary['Kr']:.1f} | {summary['Kh']:.1f} |\n"
        f"| Shear G  | {summary['Gv']:.1f} | {summary['Gr']:.1f} | {summary['Gh']:.1f} |\n"
        f"| Young E (Hill) | {summary['E_Hill']:.1f} GPa |\n"
        f"| Poisson ν (Hill) | {summary['nu_Hill']:.3f} |\n",
        encoding="utf-8",
    )
    return out_path
