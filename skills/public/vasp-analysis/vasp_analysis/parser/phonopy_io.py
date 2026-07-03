"""phonopy output parser (band.yaml / mesh.yaml / FORCE_SETS)."""
from __future__ import annotations

from pathlib import Path


def load_band_yaml(path: str | Path):
    """Load phonopy band.yaml as a dict."""
    import yaml

    path = Path(path)
    with path.open("r") as f:
        return yaml.safe_load(f)


def load_mesh_yaml(path: str | Path):
    import yaml

    path = Path(path)
    with path.open("r") as f:
        return yaml.safe_load(f)


def has_imaginary_modes(band_yaml: dict, tol_thz: float = -0.1) -> bool:
    """Return True if any frequency in band.yaml dips below tol_thz (THz)."""
    for phonon in band_yaml.get("phonon", []):
        for band in phonon.get("band", []):
            if band.get("frequency", 0.0) < tol_thz:
                return True
    return False
