"""PCM / SMD / CPCM solvation keywords.

Stub — full solvent list + dielectric overrides to be migrated from
legacy `gaussian_agent.input_sets.solvation` in Step 4.
"""

from __future__ import annotations

_SOLVENT_ALIASES = {
    "water": "Water",
    "h2o": "Water",
    "methanol": "Methanol",
    "ethanol": "Ethanol",
    "dcm": "Dichloromethane",
    "dmf": "N,N-DiMethylFormamide",
    "dmso": "DiMethylSulfoxide",
    "thf": "TetraHydroFuran",
    "acetonitrile": "Acetonitrile",
    "chloroform": "Chloroform",
    "toluene": "Toluene",
    "benzene": "Benzene",
    "hexane": "n-Hexane",
}


def scrf_keyword(model: str = "SMD", solvent: str | None = None) -> str:
    """Build an SCRF=(Model, Solvent=X) keyword string.

    model: "SMD" | "PCM" | "CPCM" | "IEFPCM"
    solvent: name; resolved against common aliases.
    """
    if solvent is None:
        return f"SCRF=({model})"
    resolved = _SOLVENT_ALIASES.get(solvent.lower(), solvent)
    return f"SCRF=({model},Solvent={resolved})"
