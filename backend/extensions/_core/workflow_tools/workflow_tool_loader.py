from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
import tempfile
import textwrap
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, create_model

from deerflow.skills.dependencies import ensure_shared_skill_venv
from extensions._core.workflow_tools.schema_utils import tool_args_schema_to_parameters

logger = logging.getLogger(__name__)

_TOOL_PY_FRAME_RE = re.compile(r'File\s+["\'][^"\']*tool\.py["\'],\s*line\s+(\d+)', re.IGNORECASE)


def parse_script_error_line(text: str) -> int | None:
    """Extract 1-based line number in user tool.py from traceback or error text."""
    if not text:
        return None
    frames = [int(m.group(1)) for m in _TOOL_PY_FRAME_RE.finditer(text)]
    if frames:
        return frames[-1]
    generic = re.search(r"line\s+(\d+)", text, re.IGNORECASE)
    if generic:
        line = int(generic.group(1))
        if 0 < line < 10_000:
            return line
    return None


def _tool_subprocess_error(data: dict[str, Any]) -> RuntimeError:
    err = str(data.get("error") or "Tool execution failed")
    tb = str(data.get("traceback") or "").strip()
    if tb:
        return RuntimeError(f"{err}\n{tb}")
    return RuntimeError(err)


_BOOTSTRAP = textwrap.dedent(
    """
    import importlib.util
    import inspect
    import json
    import sys
    from pathlib import Path

    from langchain_core.tools import BaseTool

    def _find_tool(mod):
        if hasattr(mod, "workflow_tool") and isinstance(mod.workflow_tool, BaseTool):
            return mod.workflow_tool
        tools = []
        for _name, obj in vars(mod).items():
            if isinstance(obj, BaseTool):
                tools.append(obj)
        if len(tools) == 1:
            return tools[0]
        if len(tools) > 1:
            raise RuntimeError("Multiple @tool definitions found; export exactly one or set workflow_tool")
        raise RuntimeError("No @tool found in script")

    def main():
        mode = sys.argv[1]
        tool_dir = Path(sys.argv[2])
        expected_name = sys.argv[3] if len(sys.argv) > 3 else ""
        spec = importlib.util.spec_from_file_location("workflow_user_tool", tool_dir / "tool.py")
        if spec is None or spec.loader is None:
            raise RuntimeError("Could not load tool.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        tool = _find_tool(mod)
        if expected_name and tool.name != expected_name:
            raise RuntimeError(f"Tool name mismatch: @tool name is {tool.name!r}, expected {expected_name!r}")

        if mode == "metadata":
            schema = None
            if tool.args_schema is not None:
                if hasattr(tool.args_schema, "model_json_schema"):
                    schema = tool.args_schema.model_json_schema()
                elif hasattr(tool.args_schema, "schema"):
                    schema = tool.args_schema.schema()
            out = {
                "name": tool.name,
                "description": tool.description or "",
                "schema": schema,
            }
            print(json.dumps(out, ensure_ascii=False))
            return

        if mode == "invoke":
            if len(sys.argv) > 4 and sys.argv[4]:
                import os
                os.environ["WORKFLOW_TOOL_INPUT_DIR"] = sys.argv[4]
            if len(sys.argv) > 5 and sys.argv[5]:
                import os
                out_dir = sys.argv[5]
                os.environ["WORKFLOW_TOOL_OUTPUT_DIR"] = out_dir
                os.makedirs(out_dir, exist_ok=True)
                os.chdir(out_dir)
            raw = sys.stdin.read()
            args = json.loads(raw) if raw.strip() else {}
            if tool.args_schema is not None:
                try:
                    validated = tool.args_schema.model_validate(args)
                    args = validated.model_dump(exclude_unset=True)
                except Exception:
                    pass
            if hasattr(tool, "ainvoke"):
                import asyncio
                result = asyncio.run(tool.ainvoke(args))
            elif hasattr(tool, "invoke"):
                result = tool.invoke(args)
            elif callable(tool):
                result = tool(**args) if isinstance(args, dict) else tool(args)
            else:
                raise RuntimeError("Tool is not invokable")
            print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, default=str))
            return

        raise RuntimeError(f"Unknown mode: {mode}")

    if __name__ == "__main__":
        try:
            main()
        except Exception as e:
            import traceback
            print(json.dumps({"ok": False, "error": str(e), "traceback": traceback.format_exc()}))
            sys.exit(1)
    """
)


def _write_tool_dir(script: str) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="wf_tool_"))
    (tmp / "tool.py").write_text(script, encoding="utf-8")
    return tmp


def _run_bootstrap(
    mode: str,
    script: str,
    expected_name: str,
    stdin: str | None = None,
    *,
    tool_id: str | None = None,
    input_dir: str | None = None,
    output_dir: str | None = None,
) -> dict[str, Any]:
    python_bin = ensure_shared_skill_venv()
    tool_dir = _write_tool_dir(script)
    try:
        cmd = [str(python_bin), "-c", _BOOTSTRAP, mode, str(tool_dir), expected_name]
        if tool_id:
            from extensions._core.workflow_tools.workflow_tool_test_io import (
                tool_test_inputs_dir,
                tool_test_outputs_dir,
            )

            cmd.extend([str(tool_test_inputs_dir(tool_id)), str(tool_test_outputs_dir(tool_id))])
        elif input_dir is not None or output_dir is not None:
            cmd.extend([input_dir or "", output_dir or ""])
        proc = subprocess.run(
            cmd,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=120,
        )
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        if not stdout:
            raise RuntimeError(stderr or f"Tool subprocess failed with code {proc.returncode}")
        data = json.loads(stdout)
        if isinstance(data, dict) and data.get("ok") is False:
            raise _tool_subprocess_error(data)
        if proc.returncode != 0 and isinstance(data, dict) and data.get("error"):
            raise _tool_subprocess_error(data)
        return data
    finally:
        import shutil

        shutil.rmtree(tool_dir, ignore_errors=True)


def load_tool_metadata(script: str, expected_name: str, tool_id: str | None = None) -> dict[str, Any]:
    return _run_bootstrap("metadata", script, expected_name, tool_id=tool_id)


def invoke_tool_script(
    script: str,
    expected_name: str,
    arguments: dict[str, Any],
    *,
    tool_id: str | None = None,
    input_dir: str | None = None,
    output_dir: str | None = None,
) -> Any:
    data = _run_bootstrap(
        "invoke",
        script,
        expected_name,
        json.dumps(arguments, ensure_ascii=False),
        tool_id=tool_id,
        input_dir=input_dir,
        output_dir=output_dir,
    )
    if data.get("ok"):
        return data.get("result")
    raise RuntimeError(data.get("error") or "invoke failed")


def _schema_to_pydantic(json_schema: dict[str, Any] | None) -> type[BaseModel] | None:
    if not json_schema or not isinstance(json_schema, dict):
        return None
    props = json_schema.get("properties") or {}
    if not isinstance(props, dict) or not props:
        return None
    required = set(json_schema.get("required") or [])
    fields: dict[str, Any] = {}
    for name, prop in props.items():
        if not isinstance(prop, dict):
            continue
        default_val = prop.get("default")
        py_type = str
        t = prop.get("type")
        if t == "integer":
            py_type = int
        elif t == "number":
            py_type = float
        elif t == "boolean":
            py_type = bool
        elif default_val is not None:
            if isinstance(default_val, bool):
                py_type = bool
            elif isinstance(default_val, int) and not isinstance(default_val, bool):
                py_type = int
            elif isinstance(default_val, float):
                py_type = float
        if name in required:
            fields[name] = (py_type, Field(description=prop.get("description") or ""))
        elif default_val is not None:
            fields[name] = (py_type, Field(default=default_val, description=prop.get("description") or ""))
        else:
            fields[name] = (py_type | None, Field(default=None, description=prop.get("description") or ""))
    if not fields:
        return None
    return create_model("WorkflowToolArgs", **fields)


class ScriptWorkflowTool(BaseTool):
    """LangChain tool wrapper that invokes user @tool script in shared venv subprocess."""

    def __init__(
        self,
        *,
        name: str,
        description: str,
        script: str,
        expected_name: str,
        args_schema: type[BaseModel] | None = None,
    ) -> None:
        super().__init__(name=name, description=description, args_schema=args_schema)
        self._script = script
        self._expected_name = expected_name

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        from extensions._core.workflow_tools.schema_utils import (
            prepare_tool_invoke_params,
        )

        params = prepare_tool_invoke_params(
            kwargs,
            tool_args_schema_to_parameters(self),
        )
        return invoke_tool_script(self._script, self._expected_name, params)

    async def _arun(self, *args: Any, **kwargs: Any) -> Any:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self._run(*args, **kwargs))


def build_script_tool(script: str, expected_name: str) -> ScriptWorkflowTool:
    meta = load_tool_metadata(script, expected_name)
    schema = meta.get("schema")
    args_schema = _schema_to_pydantic(schema if isinstance(schema, dict) else None)
    return ScriptWorkflowTool(
        name=str(meta.get("name") or expected_name),
        description=str(meta.get("description") or ""),
        script=script,
        expected_name=expected_name,
        args_schema=args_schema,
    )


def metadata_to_cached_schema(meta: dict[str, Any]) -> dict[str, Any]:
    schema = meta.get("schema")
    parameters = []
    if isinstance(schema, dict):
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        from extensions._core.workflow_tools.schema_utils import _prop_to_parameter

        for pname, prop in props.items():
            if isinstance(prop, dict):
                parameters.append(_prop_to_parameter(pname, prop, required))
    return {
        "parameters": parameters,
        "properties": schema.get("properties") if isinstance(schema, dict) else {},
        "required": schema.get("required") if isinstance(schema, dict) else [],
    }


def parse_missing_module(error_text: str) -> str | None:
    match = re.search(r"No module named ['\"]([^'\"]+)['\"]", error_text)
    if not match:
        return None
    top = match.group(1).split(".")[0]
    return top or None
