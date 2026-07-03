# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Resolve workflow worker paths for run_skill (never use sandbox /mnt paths)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from deerflow.skills.loader import get_skills_root_path

from extensions._core.workflow.workflow_output_paths import is_file_ref, resolve_file_value

_PATH_LIKE = re.compile(r"(?<!nodes)(/[^\s\"']+)")
_WORKFLOW_REL_PATH = re.compile(r"nodes/[^\s\"']+")
_TEMPLATE_VAR = re.compile(r"\{\{([^}]+)\}\}")
_STRUCTURE_REF_KEYS = ("poscar_path", "poscar", "structure", "contcar")


def resolve_shared_vasp_config() -> Path | None:
    """Host path to skills/public/_shared-vasp/config.yaml (same fallback as vasp_skills_lib)."""
    sandbox = Path("/mnt/skills/public/_shared-vasp/config.yaml")
    if sandbox.is_file():
        return sandbox.resolve()
    repo = get_skills_root_path() / "public" / "_shared-vasp" / "config.yaml"
    if repo.is_file():
        return repo.resolve()
    return None


def resolve_vasp_executor() -> str:
    """Default HPC executor for workflow VASP skills (scnet unless configured)."""
    env = os.environ.get("WORKFLOW_VASP_EXECUTOR", "").strip()
    if env:
        return env
    try:
        from extensions._core.config.loader import load_yaml_config

        for name in ("conf.yaml", "config.yaml"):
            cfg = load_yaml_config(name)
            wf = cfg.get("workflow") or {}
            vasp = wf.get("vasp") or {}
            ex = vasp.get("executor")
            if isinstance(ex, str) and ex.strip():
                return ex.strip()
    except Exception:
        pass
    return "scnet"


def workflow_vasp_dry_run() -> bool:
    return os.environ.get("WORKFLOW_VASP_DRY_RUN", "").strip().lower() in ("1", "true", "yes")


def resolve_workflow_work_dir(work_dir: str | None, ctx: dict[str, Any]) -> Path:
    """Map LLM-provided work_dir to a writable directory under workflow work_root."""
    work_root = ctx.get("work_root")
    default_dir = ctx.get("default_work_dir")
    raw = str(work_dir or "").strip()

    if work_root:
        root = Path(str(work_root)).resolve()
        fallback = Path(str(default_dir)).resolve() if default_dir else root / "nodes" / str(
            ctx.get("workflow_node_id") or "step"
        )
        if not raw or raw.startswith("/mnt") or "user-data" in raw or raw.startswith("~"):
            return fallback
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = (root / candidate).resolve()
        else:
            candidate = candidate.resolve()
        if str(candidate).startswith("/mnt"):
            return fallback
        try:
            candidate.relative_to(root)
            return candidate
        except ValueError:
            return fallback

    if raw:
        p = Path(raw).expanduser()
        if str(p).startswith("/mnt"):
            if default_dir:
                return Path(str(default_dir)).resolve()
            raise ValueError(f"Invalid work_dir (sandbox path not allowed on workflow worker): {raw}")
        return p.resolve()
    if default_dir:
        return Path(str(default_dir)).resolve()
    raise ValueError("work_dir is required when work_root is not set in workflow context")


def _path_from_value(val: Any, work_root: str | None) -> str | None:
    if val is None:
        return None
    if is_file_ref(val) and work_root:
        abs_p = resolve_file_value(work_root, val)
        if isinstance(abs_p, str) and Path(abs_p).is_file():
            return abs_p
    if isinstance(val, str) and val.strip():
        text = val.strip().strip('"').strip("'")
        p = Path(text).expanduser()
        if not p.is_absolute() and work_root:
            p = (Path(work_root) / text.lstrip("/")).resolve()
        elif not p.is_absolute():
            return None
        else:
            p = p.resolve()
        if p.is_file():
            return str(p)
    return None


def find_structure_path(
    *,
    node_outputs: dict[str, Any] | None,
    work_root: str | None,
    prompt: str | None = None,
    ctx: dict[str, Any] | None = None,
) -> str | None:
    """POSCAR/structure absolute path from start node outputs or resolved prompt."""
    if ctx and ctx.get("structure_path"):
        sp = str(ctx["structure_path"])
        if Path(sp).is_file():
            return str(Path(sp).resolve())

    if node_outputs:
        for out in node_outputs.values():
            if not isinstance(out, dict):
                continue
            for key in ("output", "input"):
                block = out.get(key)
                if isinstance(block, dict):
                    for val in block.values():
                        found = _path_from_value(val, work_root)
                        if found:
                            return found
                    for field in ("poscar_path", "poscar", "structure", "contcar", "input"):
                        found = _path_from_value(block.get(field), work_root)
                        if found:
                            return found
                found = _path_from_value(block, work_root)
                if found:
                    return found

    if prompt:
        for line in prompt.splitlines():
            line = line.strip()
            if not line or line.startswith("{{"):
                continue
            found = _path_from_value(line, work_root)
            if found:
                return found
        text = prompt.strip().strip('"').strip("'")
        if text and (text.startswith("/") or text.startswith("~")) and Path(text).is_file():
            return str(Path(text).expanduser().resolve())
        for rel in _WORKFLOW_REL_PATH.findall(prompt):
            found = _path_from_value(rel, work_root)
            if found:
                return found
        for match in _PATH_LIKE.findall(prompt):
            p = Path(match)
            if not p.is_absolute() and work_root:
                p = (Path(work_root) / str(match).lstrip("/")).resolve()
            if p.is_file() and (
                "POSCAR" in p.name.upper()
                or p.name.upper() in ("POSCAR", "CONTCAR", "POTCAR")
                or p.suffix.lower() in (".vasp", ".poscar")
            ):
                return str(p)

    return None


def extract_file_refs_from_prompt(
    prompt: str | None,
    *,
    node_outputs: dict[str, Any] | None,
    node_labels: dict[str, str] | None = None,
    work_root: str | None = None,
    node_aliases: dict[str, str] | None = None,
) -> dict[str, str]:
    """Resolve {{node.output.field}} in prompt to absolute file paths (execution layer)."""
    if not prompt or not node_outputs:
        return {}
    from extensions._core.workflow.runtime.template_parser import render_template

    refs: dict[str, str] = {}
    for match in _TEMPLATE_VAR.finditer(prompt):
        var_path = match.group(1).strip()
        rendered = render_template(
            f"{{{{{var_path}}}}}",
            node_outputs,
            node_labels,
            work_root=work_root,
            node_aliases=node_aliases,
            file_path_style="absolute",
        )
        if rendered.startswith("{{"):
            continue
        found = _path_from_value(rendered, work_root)
        if not found:
            continue
        key = var_path.split(".", 1)[-1]
        if key.startswith("output."):
            key = key[len("output.") :]
        elif key.startswith("input."):
            key = key[len("input.") :]
        refs[key] = found
    return refs


def structure_path_from_refs(file_refs: dict[str, str]) -> str | None:
    for key in _STRUCTURE_REF_KEYS:
        path = file_refs.get(key)
        if path and Path(path).is_file():
            return path
    for path in file_refs.values():
        if path and Path(path).is_file():
            name = Path(path).name.upper()
            if "POSCAR" in name or name in ("POSCAR", "CONTCAR", "POTCAR"):
                return path
    return None


def build_skill_argv_from_refs(
    skill_name: str,
    structure_path: str,
    work_dir: Path,
    file_refs: dict[str, str] | None = None,
) -> list[str]:
    argv = default_skill_argv(skill_name, structure_path, work_dir)
    refs = file_refs or {}
    if skill_name == "vasp-relax":
        potcar = refs.get("potcar") or refs.get("POTCAR")
        if potcar and Path(potcar).is_file():
            argv.extend(["--potcar", potcar])
    return argv


def default_skill_argv(skill_name: str, structure_path: str, work_dir: Path) -> list[str]:
    if skill_name == "vasp-potcar":
        return ["workflow", structure_path, "-o", str(work_dir / "POTCAR")]
    if skill_name == "vasp-relax":
        argv: list[str] = [
            structure_path,
            "--work-dir",
            str(work_dir),
        ]
        vasp_cfg = resolve_shared_vasp_config()
        if vasp_cfg is not None:
            argv.extend(["--config", str(vasp_cfg)])
        argv.extend(["--executor", resolve_vasp_executor()])
        if workflow_vasp_dry_run():
            argv.append("--dry-run")
        return argv
    return [structure_path]
