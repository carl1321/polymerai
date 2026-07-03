"""Higher-level preset helpers that bundle (method, basis, keyword) triples.

Replaces the 45-class `InputSet` hierarchy of the legacy `gaussian_agent` with
parameterized builders. Add new presets here as dicts, not classes.
"""

from __future__ import annotations

from .route import Route

# Common method/basis pairings. Override via kwargs in the builder.
PRESETS: dict[str, dict] = {
    "b3lyp-d3": {"method": "B3LYP", "basis": "6-31G(d)", "extra": ["EmpiricalDispersion=GD3"]},
    "m062x": {"method": "M062X", "basis": "6-31+G(d,p)", "extra": []},
    "wb97xd": {"method": "wB97XD", "basis": "def2SVP", "extra": []},
    "mp2": {"method": "MP2", "basis": "6-311+G(d,p)", "extra": []},
    "hf-sto3g": {"method": "HF", "basis": "STO-3G", "extra": []},
}


def build_route(
    calc_type: str,
    preset: str = "b3lyp-d3",
    *,
    method: str | None = None,
    basis: str | None = None,
    extra_keywords: list[str] | None = None,
) -> Route:
    """Build a Route for a given calculation type.

    calc_type: "opt" | "freq" | "optfreq" | "ts" | "irc" | "tddft" | "scan" | "nmr" | "sp"
    preset: key in PRESETS; ignored if method/basis explicit.
    """
    base = PRESETS.get(preset, PRESETS["b3lyp-d3"])
    m = method or base["method"]
    b = basis if basis is not None else base["basis"]
    kws = list(base.get("extra", []))

    calc_kws = {
        "opt": ["Opt"],
        "freq": ["Freq"],
        "optfreq": ["Opt", "Freq"],
        "ts": ["Opt=(TS,CalcFC,NoEigenTest)", "Freq"],
        "irc": ["IRC=(CalcFC,MaxPoints=50)"],
        "tddft": ["TD=(NStates=10,Singlets)"],
        "scan": ["Opt=ModRedundant"],
        "nmr": ["NMR=GIAO"],
        "sp": [],
    }.get(calc_type, [])
    kws = calc_kws + kws
    if extra_keywords:
        kws.extend(extra_keywords)
    return Route(method=m, basis=b, keywords=kws)
