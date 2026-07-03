from __future__ import annotations

from typing import Any


def node_label_from_data(data: Any, node_id: str) -> str:
    """Programmatic node name for {{node.field}} templates (prefer taskName)."""
    if data is None:
        return str(node_id)
    if isinstance(data, dict):
        for key in ("taskName", "task_name", "nodeName", "node_name", "label"):
            val = data.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
        return str(node_id)
    for attr in ("task_name", "taskName", "node_name", "nodeName", "label"):
        if hasattr(data, attr):
            val = getattr(data, attr)
            if val is not None and str(val).strip():
                return str(val).strip()
    return str(node_id)


def read_node_data_field(data: Any, *keys: str) -> Any:
    """Read first non-empty value from node.data by camel/snake key aliases."""
    if data is None:
        return None
    if isinstance(data, dict):
        for key in keys:
            val = data.get(key)
            if val is not None and str(val).strip():
                return val
        return None
    for key in keys:
        if hasattr(data, key):
            val = getattr(data, key)
            if val is not None and str(val).strip():
                return val
    return None
