"""Shared plotter utilities: stylesheet loading, output path handling."""
from __future__ import annotations

from pathlib import Path

_STYLE_PATH = Path(__file__).parent.parent / "styles" / "default.mplstyle"


def apply_style() -> None:
    """Apply the skill's default matplotlib stylesheet."""
    import matplotlib.pyplot as plt

    if _STYLE_PATH.is_file():
        plt.style.use(str(_STYLE_PATH))


def resolve_output(workdir: Path, name: str, fmt: str = "png") -> Path:
    """Return workdir/name.fmt, ensuring the parent exists."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    return workdir / f"{name}.{fmt}"


def save_figure(fig, out_path: Path) -> Path:
    """Save a matplotlib Figure to `out_path` at the configured dpi."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    return out_path
