from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from deerflow.config.paths import get_paths

DEFAULT_OUTPUT_BASENAME = "result.out"


def default_output_relative(filename: str | None = None) -> str:
    """Default relative path for tool output files (under outputs/)."""
    name = Path(filename or DEFAULT_OUTPUT_BASENAME).name
    if not name:
        name = DEFAULT_OUTPUT_BASENAME
    return f"outputs/{name}"


def tool_test_root(tool_id: str) -> Path:
    root = get_paths().sandbox_shared_dir() / "workflow-tools-test" / tool_id
    root.mkdir(parents=True, exist_ok=True)
    return root


def tool_test_inputs_dir(tool_id: str) -> Path:
    d = tool_test_root(tool_id) / "inputs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def tool_test_outputs_dir(tool_id: str) -> Path:
    d = tool_test_root(tool_id) / "outputs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def clear_test_outputs(tool_id: str) -> None:
    out = tool_test_outputs_dir(tool_id)
    if out.exists():
        shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)


def _is_bare_filename(text: str) -> bool:
    return bool(text) and "/" not in text and "\\" not in text and not text.startswith(".")


def _path_is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def resolve_under_tool_test(tool_id: str, relative: str) -> Path | None:
    """Resolve relative path (inputs/foo, outputs/bar, or bare filename) under tool test workspace."""
    rel = relative.strip().lstrip("/").replace("\\", "/")
    if not rel or ".." in rel.split("/"):
        return None
    if _is_bare_filename(rel):
        rel = f"outputs/{rel}"
    root = tool_test_root(tool_id).resolve()
    candidate = (root / rel).resolve()
    if not _path_is_under(candidate, root):
        return None
    return candidate


def stage_artifact_into_workspace(tool_id: str, path: Path) -> str | None:
    """Ensure file is under tool test workspace; copy into outputs/ when needed."""
    if not path.is_file():
        return None
    root = tool_test_root(tool_id).resolve()
    resolved = path.resolve()
    if _path_is_under(resolved, root):
        return resolved.relative_to(root).as_posix()
    dest = tool_test_outputs_dir(tool_id) / resolved.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if resolved != dest:
        shutil.copy2(resolved, dest)
    return f"outputs/{resolved.name}"


def find_artifact_path(tool_id: str, text: str) -> Path | None:
    """Locate a file referenced by tool return value or parameter."""
    text = text.strip()
    if not text:
        return None
    p = Path(text)
    if p.is_absolute() and p.is_file():
        return p.resolve()
    if text.startswith("inputs/") or text.startswith("outputs/"):
        resolved = resolve_under_tool_test(tool_id, text)
        return resolved if resolved and resolved.is_file() else None
    if _is_bare_filename(text):
        for cand in (
            tool_test_outputs_dir(tool_id) / text,
            tool_test_root(tool_id) / text,
        ):
            if cand.is_file():
                return cand.resolve()
        # Legacy: written to gateway cwd before chdir fix
        cwd_file = Path.cwd() / text
        if cwd_file.is_file():
            return cwd_file.resolve()
    resolved = resolve_under_tool_test(tool_id, text)
    return resolved if resolved and resolved.is_file() else None


def save_uploaded_input(tool_id: str, filename: str, content: bytes) -> dict[str, str]:
    safe = Path(filename).name
    if not safe:
        safe = "file"
    dest = tool_test_inputs_dir(tool_id) / safe
    dest.write_bytes(content)
    rel = f"inputs/{safe}"
    return {
        "filename": safe,
        "path": str(dest),
        "relativePath": rel,
    }


def list_output_files(tool_id: str) -> list[dict[str, str]]:
    out_dir = tool_test_outputs_dir(tool_id)
    files: list[dict[str, str]] = []
    if not out_dir.exists():
        return files
    for f in sorted(out_dir.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(out_dir).as_posix()
        files.append({"filename": f.name, "relativePath": f"outputs/{rel}"})
    return files


def collect_output_artifacts(tool_id: str, result: Any) -> list[dict[str, str]]:
    """Merge scanned output dir files with explicit path in tool return value."""
    seen: set[str] = set()
    items: list[dict[str, str]] = []

    def add_path(path: Path) -> None:
        rel = stage_artifact_into_workspace(tool_id, path)
        if not rel:
            return
        key = str((tool_test_root(tool_id) / rel).resolve())
        if key in seen:
            return
        seen.add(key)
        items.append({"filename": Path(rel).name, "relativePath": rel})

    for entry in list_output_files(tool_id):
        p = resolve_under_tool_test(tool_id, entry["relativePath"])
        if p:
            add_path(p)

    texts: list[str] = []
    if isinstance(result, str) and result.strip():
        texts.append(result.strip())
    elif isinstance(result, dict):
        for key in ("path", "file", "output_path", "output_file", "filepath"):
            val = result.get(key)
            if isinstance(val, str) and val.strip():
                texts.append(val.strip())

    for text in texts:
        found = find_artifact_path(tool_id, text)
        if found:
            add_path(found)

    return items


def enrich_params_with_uploaded_paths(tool_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """Resolve input paths; fill default output_file when empty."""
    out = dict(params)
    inputs = tool_test_inputs_dir(tool_id)
    for key, val in list(out.items()):
        if isinstance(val, str) and not val.strip():
            if key in ("output_file", "output_path", "output", "out_file"):
                out[key] = default_output_relative()
            continue
        if not isinstance(val, str) or not val.strip():
            continue
        text = val.strip()
        if text.startswith("inputs/") or text.startswith("outputs/"):
            resolved = resolve_under_tool_test(tool_id, text)
            if resolved and resolved.is_file():
                out[key] = str(resolved)
            continue
        if text.startswith("/"):
            p = Path(text)
            if p.is_file():
                out[key] = str(p)
            continue
        candidate = inputs / Path(text).name
        if candidate.is_file():
            out[key] = str(candidate)
    return out
