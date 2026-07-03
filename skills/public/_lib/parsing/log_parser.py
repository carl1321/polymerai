"""cclib-based Gaussian `.log` parser.

Thin wrapper that normalizes cclib output into a plain dict friendly to
downstream skills. Do not add skill-specific logic here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def parse_log(log_path: str | Path) -> dict[str, Any]:
    """Parse a Gaussian `.log` into a dict.

    Returns at minimum:
        - normal_termination: bool
        - final_energy: float (Hartree) or None
        - scf_energies: list[float]
        - geometries: list[np.ndarray] (Nsteps x Natoms x 3)
        - atoms: list[int] (atomic numbers)
        - frequencies: list[float] or None
        - thermochemistry: {zpe, enthalpy, gibbs, temperature} or None
        - raw_cclib: underlying cclib data object (for escape hatch)
    """
    import cclib

    log_path = Path(log_path)
    data = cclib.io.ccread(str(log_path))
    if data is None:
        return {
            "normal_termination": False,
            "final_energy": None,
            "error": f"cclib could not parse {log_path}",
        }

    def _last(attr: str):
        v = getattr(data, attr, None)
        if v is None:
            return None
        try:
            return float(v[-1])
        except (TypeError, IndexError):
            return None

    result: dict[str, Any] = {
        "normal_termination": bool(getattr(data, "metadata", {}).get("success", False)),
        "final_energy": _last("scfenergies"),  # eV in cclib; convert below
        "scf_energies": list(getattr(data, "scfenergies", []) or []),
        "atoms": list(getattr(data, "atomnos", []) or []),
        "geometries": getattr(data, "atomcoords", None),
        "frequencies": list(getattr(data, "vibfreqs", []) or []) or None,
        "raw_cclib": data,
    }

    # cclib returns SCF energies in eV; convert to Hartree for Gaussian convention.
    eV_to_Ha = 1.0 / 27.211386245988
    if result["final_energy"] is not None:
        result["final_energy"] *= eV_to_Ha
    if result["scf_energies"]:
        result["scf_energies"] = [e * eV_to_Ha for e in result["scf_energies"]]

    thermo_keys = ("enthalpy", "entropy", "freeenergy", "zpve", "temperature")
    thermo = {k: getattr(data, k, None) for k in thermo_keys}
    if any(v is not None for v in thermo.values()):
        result["thermochemistry"] = thermo

    return result
