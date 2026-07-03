"""Per-tag explainer: meaning, default, recommended range, related tags."""
from __future__ import annotations

from pathlib import Path
from typing import Any


_CACHE: dict[str, Any] | None = None


def _load() -> dict[str, Any]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    import yaml

    path = Path(__file__).parent / "references" / "incar_params.yaml"
    if not path.is_file():
        _CACHE = {}
        return _CACHE
    _CACHE = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _CACHE


def explain(tag: str) -> str:
    db = _load()
    key = tag.upper()
    entry = db.get(key)
    if not entry:
        return (
            f"{key}: no entry in references/incar_params.yaml. "
            "Consult the VASP wiki for full documentation."
        )
    lines = [f"# {key}"]
    for k in ("meaning", "default", "recommended", "notes", "related"):
        if k in entry:
            lines.append(f"- **{k}**: {entry[k]}")
    return "\n".join(lines)
