"""Auto-mode: detect calc type → run all relevant plotters + summary."""
from __future__ import annotations

from pathlib import Path

from ..detector import detect


def run(workdir: str | Path, *, fmt: str = "png") -> dict[str, Path]:
    """Detect, then dispatch. Returns a dict of {kind: output_path}."""
    workdir = Path(workdir)
    result = detect(workdir)
    products: dict[str, Path] = {}

    # Always write a summary
    try:
        from ..reporters.summary import write as write_summary

        products["summary"] = write_summary(workdir)
    except Exception as exc:
        products["summary"] = Path(f"<failed: {exc}>")

    calc = result.calc_type
    try:
        if calc == "band":
            from ..plotters.band import plot as plot_band

            products["band"] = plot_band(workdir, fmt=fmt)
        elif calc == "band_dos":
            from ..plotters.band_dos import plot as plot_bd

            products["band_dos"] = plot_bd(workdir, fmt=fmt)
        elif calc == "dos":
            from ..plotters.dos import plot as plot_dos

            products["dos"] = plot_dos(workdir, element=True, fmt=fmt)
        elif calc == "phonon":
            from ..plotters.phonon import plot as plot_phonon

            products["phonon"] = plot_phonon(workdir, fmt=fmt)
        elif calc == "elastic":
            from ..plotters.elastic import plot as plot_elastic

            products["elastic"] = plot_elastic(workdir, fmt=fmt)
        elif calc == "optical":
            from ..plotters.optical import plot as plot_optical

            products["optical"] = plot_optical(workdir, fmt=fmt)
    except Exception as exc:
        products[calc] = Path(f"<failed: {exc}>")

    products["_detection"] = Path(str(result))
    return products
