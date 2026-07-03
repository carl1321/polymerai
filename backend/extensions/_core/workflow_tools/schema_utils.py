from __future__ import annotations

from typing import Any


def _prop_to_parameter(name: str, prop: dict[str, Any], required: set[str]) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": name,
        "type": prop.get("type", "string"),
        "description": prop.get("description", ""),
        "required": name in required,
    }
    if "default" in prop:
        entry["default"] = prop["default"]
    return entry


def tool_args_schema_to_parameters(tool: Any) -> list[dict[str, Any]]:
    """Serialize LangChain tool args_schema to workflow ToolDefinition parameters."""
    parameters: list[dict[str, Any]] = []
    schema = getattr(tool, "args_schema", None)
    json_schema = None
    if schema is not None and hasattr(schema, "model_json_schema"):
        json_schema = schema.model_json_schema()
    elif schema is not None and hasattr(schema, "schema"):
        json_schema = schema.schema()
    props = (json_schema or {}).get("properties", {})
    required = set((json_schema or {}).get("required", []))
    for name, prop in props.items():
        if isinstance(prop, dict):
            parameters.append(_prop_to_parameter(name, prop, required))
    return parameters


def cached_schema_to_parameters(cached_schema: Any) -> list[dict[str, Any]]:
    if not isinstance(cached_schema, dict):
        return []
    props = cached_schema.get("properties", {})
    required = set(cached_schema.get("required", []))
    props_dict = props if isinstance(props, dict) else {}

    params = cached_schema.get("parameters")
    if isinstance(params, list) and params:
        enriched: list[dict[str, Any]] = []
        for p in params:
            if not isinstance(p, dict) or not p.get("name"):
                continue
            name = str(p["name"])
            prop = props_dict.get(name, {})
            entry = dict(p)
            if "default" not in entry and isinstance(prop, dict) and "default" in prop:
                entry["default"] = prop["default"]
            enriched.append(entry)
        return enriched

    if not props_dict:
        return []
    out: list[dict[str, Any]] = []
    for name, prop in props_dict.items():
        if isinstance(prop, dict):
            out.append(_prop_to_parameter(name, prop, required))
    return out


def resolve_workflow_file_ref(value: Any, work_root: str | None) -> Any:
    """Turn {\"file\": \"rel\"} (or JSON string) into absolute path for tool args."""
    from extensions._core.workflow.workflow_output_paths import is_file_ref, resolve_file_value

    if not work_root:
        return value
    if is_file_ref(value):
        resolved = resolve_file_value(work_root, value)
        return resolved if isinstance(resolved, str) else value
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("{") and '"file"' in text:
            import json

            try:
                parsed = json.loads(text)
                if is_file_ref(parsed):
                    resolved = resolve_file_value(work_root, parsed)
                    return resolved if isinstance(resolved, str) else value
            except json.JSONDecodeError:
                pass
    return value


def _infer_param_type(param_type: str, default: Any) -> str:
    if param_type and param_type != "string":
        return param_type
    if isinstance(default, bool):
        return "boolean"
    if isinstance(default, int) and not isinstance(default, bool):
        return "integer"
    if isinstance(default, float):
        return "number"
    return param_type or "string"


def prepare_tool_invoke_params(
    params: dict[str, Any],
    parameters: list[dict[str, Any]] | None = None,
    *,
    work_root: str | None = None,
) -> dict[str, Any]:
    """Drop empty values; coerce strings to schema types for workflow tool nodes."""
    meta_by_name: dict[str, dict[str, Any]] = {}
    for p in parameters or []:
        if isinstance(p, dict) and p.get("name"):
            meta_by_name[str(p["name"])] = p
    out: dict[str, Any] = {}
    for key, val in params.items():
        if val is None:
            continue
        if isinstance(val, str) and not val.strip():
            continue
        val = resolve_workflow_file_ref(val, work_root)
        if isinstance(val, dict):
            val = resolve_workflow_file_ref(val, work_root)
        meta = meta_by_name.get(key, {})
        param_type = _infer_param_type(str(meta.get("type") or "string"), meta.get("default"))
        if isinstance(val, str):
            text = val.strip()
            try:
                if param_type == "boolean":
                    out[key] = text.lower() in ("true", "1", "yes", "on")
                elif param_type == "integer":
                    out[key] = int(float(text)) if "." in text else int(text)
                elif param_type == "number":
                    out[key] = float(text)
                else:
                    out[key] = text
            except (TypeError, ValueError):
                out[key] = text
        else:
            out[key] = val
    return out
