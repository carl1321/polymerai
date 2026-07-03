"""Database error helpers for extension APIs."""

from __future__ import annotations


def is_undefined_table(exc: BaseException) -> bool:
    """True when PostgreSQL reports a missing relation."""
    name = type(exc).__name__
    if name == "UndefinedTable":
        return True
    msg = str(exc).lower()
    return "does not exist" in msg and ("relation" in msg or "table" in msg)
