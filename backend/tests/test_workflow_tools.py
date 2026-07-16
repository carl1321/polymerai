"""Tests for global workflow tools (catalog, deps, loader)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from extensions._core.workflow_tools.db import DEFAULT_SCRIPT_TEMPLATE
from extensions._core.workflow_tools.workflow_tool_deps import (
    _is_conflict_output,
    extract_import_packages,
)
from extensions._core.workflow_tools.workflow_tool_loader import (
    metadata_to_cached_schema,
    parse_missing_module,
    parse_script_error_line,
)


def test_conflict_detection():
    assert _is_conflict_output("ERROR: ResolutionImpossible", 1) is True
    assert _is_conflict_output("Successfully installed", 0) is False


def test_parse_missing_module():
    assert parse_missing_module("No module named 'pandas'") == "pandas"
    assert parse_missing_module("other error") is None


def test_parse_script_error_line():
    tb = """Traceback (most recent call last):
  File "/tmp/wf_tool_x/tool.py", line 12, in <module>
    main()
  File "/tmp/wf_tool_x/tool.py", line 8, in smiles_build
    return 1 / 0
ZeroDivisionError: division by zero
"""
    assert parse_script_error_line(tb) == 8


def test_extract_import_packages():
    script = "import pandas as pd\nfrom langchain_core.tools import tool\nimport requests"
    pkgs = extract_import_packages(script)
    assert "pandas" in pkgs
    assert "requests" in pkgs
    assert "langchain_core" not in pkgs


def test_metadata_to_cached_schema():
    meta = {
        "schema": {
            "properties": {"query": {"type": "string", "description": "q"}},
            "required": ["query"],
        }
    }
    cached = metadata_to_cached_schema(meta)
    assert len(cached["parameters"]) == 1
    assert cached["parameters"][0]["name"] == "query"


@patch("extensions._core.workflow_tools.workflow_tool_deps.subprocess.run")
@patch("extensions._core.workflow_tools.workflow_tool_deps.ensure_shared_skill_venv")
def test_ensure_tool_requirements_aborts_on_dry_run_conflict(mock_venv, mock_run, tmp_path):
    from extensions._core.workflow_tools import workflow_tool_deps as deps

    mock_venv.return_value = tmp_path / "python"
    mock_venv.return_value.parent.mkdir(parents=True, exist_ok=True)
    mock_venv.return_value.touch()

    mock_run.return_value = MagicMock(
        returncode=1,
        stdout="",
        stderr="ResolutionImpossible: conflict",
    )

    with patch.object(deps, "_state_path", return_value=tmp_path / "state.hash"):
        result = deps.ensure_tool_requirements("tool-1", "pandas>=99\nnumpy<1")

    assert result.ok is False
    assert result.deps_error is True
    assert mock_run.call_count == 1


@patch("extensions._core.workflow_tools.workflow_tool_loader._run_bootstrap")
def test_build_script_tool(mock_bootstrap):
    from extensions._core.workflow_tools.workflow_tool_loader import build_script_tool

    mock_bootstrap.return_value = {
        "name": "demo_tool",
        "description": "demo",
        "schema": {
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    }
    script = DEFAULT_SCRIPT_TEMPLATE.format(tool_name="demo_tool", description="demo")
    tool = build_script_tool(script, "demo_tool")
    assert tool.name == "demo_tool"
    assert tool.description == "demo"
