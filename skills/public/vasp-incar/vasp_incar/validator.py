"""INCAR validator — loads rules/conflicts.yaml and reports violations.

Each rule is a dict with:

  id:   unique short tag (e.g. "ISMEAR_M1_FEW_KPT")
  severity: "error" | "warning"
  description: human-readable explanation
  condition: a mini-DSL dict; see `_evaluate` for supported keys.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Violation:
    rule_id: str
    severity: str
    message: str

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.rule_id}: {self.message}"


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in (".true.", "true", "t", ".t.")
    return bool(v)


def _get(incar: dict, key: str, default: Any = None) -> Any:
    for k in (key, key.upper(), key.lower()):
        if k in incar:
            return incar[k]
    return default


def _evaluate(cond: dict, incar: dict, context: dict) -> bool:
    """Tiny DSL.

    Supported keys (all must match for the rule to fire):
      tag_set:        {TAG: expected_value}
      tag_in:         {TAG: [v1, v2, ...]}
      tag_truthy:     [TAG, ...]
      tag_falsy:      [TAG, ...]
      tag_missing:    [TAG, ...]
      tag_gt:         {TAG: threshold}
      tag_lt:         {TAG: threshold}
      context_eq:     {key: value}           # e.g. {"n_kpoints": "lt:4"}
    """
    for tag, exp in cond.get("tag_set", {}).items():
        if _get(incar, tag) != exp:
            return False
    for tag, allowed in cond.get("tag_in", {}).items():
        if _get(incar, tag) not in allowed:
            return False
    for tag, forbidden in cond.get("tag_not_in", {}).items():
        if _get(incar, tag) in forbidden:
            return False
    for tag in cond.get("tag_truthy", []):
        if not _truthy(_get(incar, tag, False)):
            return False
    for tag in cond.get("tag_falsy", []):
        if _truthy(_get(incar, tag, False)):
            return False
    for tag in cond.get("tag_missing", []):
        if _get(incar, tag) is not None:
            return False
    for tag, thr in cond.get("tag_gt", {}).items():
        v = _get(incar, tag)
        try:
            if v is None or float(v) <= float(thr):
                return False
        except (TypeError, ValueError):
            return False
    for tag, thr in cond.get("tag_lt", {}).items():
        v = _get(incar, tag)
        try:
            if v is None or float(v) >= float(thr):
                return False
        except (TypeError, ValueError):
            return False
    for key, expr in cond.get("context_eq", {}).items():
        ctx_val = context.get(key)
        if isinstance(expr, str) and ":" in expr:
            op, rhs = expr.split(":", 1)
            try:
                rhs_n = float(rhs)
                if ctx_val is None:
                    return False
                if op == "lt" and not (float(ctx_val) < rhs_n):
                    return False
                if op == "gt" and not (float(ctx_val) > rhs_n):
                    return False
                if op == "eq" and not (float(ctx_val) == rhs_n):
                    return False
            except ValueError:
                if op == "eq" and ctx_val != rhs:
                    return False
        elif ctx_val != expr:
            return False
    return True


def load_rules(path: str | Path | None = None) -> list[dict]:
    import yaml

    if path is None:
        path = Path(__file__).parent / "rules" / "conflicts.yaml"
    path = Path(path)
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(data.get("rules", []))


def validate(incar: dict, context: dict | None = None,
             rules_path: str | Path | None = None) -> list[Violation]:
    """Run all rules. `context` may carry e.g. n_kpoints, n_atoms, is_metal."""
    context = context or {}
    out: list[Violation] = []
    for rule in load_rules(rules_path):
        try:
            if _evaluate(rule.get("condition", {}), incar, context):
                out.append(Violation(
                    rule_id=rule.get("id", "?"),
                    severity=rule.get("severity", "warning"),
                    message=rule.get("description", ""),
                ))
        except Exception as exc:
            out.append(Violation(
                rule_id=rule.get("id", "?"),
                severity="warning",
                message=f"rule evaluation failed: {exc}",
            ))
    return out


def parse_incar(path: str | Path) -> dict:
    from pymatgen.io.vasp import Incar

    return dict(Incar.from_file(str(path)))
