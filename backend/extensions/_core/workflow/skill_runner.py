# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Execute toolbox skills on the workflow worker host (not conversation sandbox)."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from deerflow.runtime.async_tasks.envelope import resolve_submit_envelope
from deerflow.skills.loader import get_skills_root_path

logger = logging.getLogger(__name__)

_SKILLS_PUBLIC_MOUNT = "/mnt/skills/public"
_SHARED_VENV_PYTHON = (
    Path(__file__).resolve().parents[3] / ".deer-flow" / ".venv" / "bin" / "python"
)


def _shared_skill_python() -> str | None:
    py = _SHARED_VENV_PYTHON
    return str(py) if py.is_file() else None


def _wrap_shell_with_shared_venv(command: str) -> str:
    py = _shared_skill_python()
    if not py:
        return command
    prefix = f'export PATH="{Path(py).parent}:$PATH"; '
    out = command
    if "pip install" in out:
        out = out.split("&&", 1)[-1].strip() if "&&" in out else out
    out = out.replace("python ", f'"{py}" ', 1).replace("python3 ", f'"{py}" ', 1)
    return prefix + out



def _skills_repo_root() -> Path:
    return get_skills_root_path()


def resolve_skill_dir(skill_name: str) -> Path:
    root = _skills_repo_root()
    for category in ("public", "custom"):
        candidate = root / category / skill_name
        if (candidate / "SKILL.md").is_file():
            return candidate
    raise FileNotFoundError(f"Skill not found on disk: {skill_name!r}")


def _rewrite_skill_paths(command: str) -> str:
    host_public = str(_skills_repo_root() / "public")
    out = command.replace(_SKILLS_PUBLIC_MOUNT, host_public)
    out = out.replace("/mnt/skills/public", host_public)
    return out


def _normalize_async_envelope_poll_command(envelope: dict[str, Any]) -> dict[str, Any]:
    """Rewrite sandbox poll_command paths to workflow worker host paths."""
    poll_raw = envelope.get("poll_command")
    if not isinstance(poll_raw, str) or not poll_raw.strip():
        return envelope
    host_public = str(_skills_repo_root() / "public")
    cmd = _rewrite_skill_paths(poll_raw.strip())
    for skill_name in ("vasp-relax", "vasp-scf", "vasp-band", "vasp-phonon"):
        poll_py = host_public + f"/{skill_name}/scripts/poll.py"
        sandbox_poll = f"{_SKILLS_PUBLIC_MOUNT}/{skill_name}/scripts/poll.py"
        if sandbox_poll in cmd:
            cmd = cmd.replace(sandbox_poll, poll_py)
        rel = f"{skill_name}/scripts/poll.py"
        if rel in cmd and poll_py not in cmd:
            cmd = cmd.replace(rel, poll_py)
    out = dict(envelope)
    out["poll_command"] = cmd
    return out


def _find_entry_script(skill_dir: Path) -> Path | None:
    run_py = skill_dir / "scripts" / "run.py"
    if run_py.is_file():
        return run_py
    for name in ("potcar.py", "run.py"):
        candidate = skill_dir / name
        if candidate.is_file():
            return candidate
    scripts = [
        p
        for p in (skill_dir / "scripts").glob("*.py")
        if p.name not in ("__init__.py", "init_mongodb.py") and p.is_file()
    ]
    if len(scripts) == 1:
        return scripts[0]
    return None


def skill_requires_detach(skill_name: str) -> bool:
    """True only for skills whose scripts/run.py submits async HPC jobs (vasp-relax, etc.)."""
    try:
        skill_dir = resolve_skill_dir(skill_name)
    except FileNotFoundError:
        return False
    run_py = skill_dir / "scripts" / "run.py"
    if not run_py.is_file():
        return False
    try:
        head = run_py.read_text(encoding="utf-8", errors="ignore")[:12000]
    except OSError:
        return False
    markers = (
        "emit_deerflow_async_envelope",
        "status=submitted",
        "detach",
        "submit_job_only",
    )
    return any(m in head for m in markers)


def _build_argv(entry: Path, argv: list[str] | None, kwargs: dict[str, Any] | None) -> list[str]:
    py = _shared_skill_python() or sys.executable
    base = [py, str(entry)]
    if argv:
        return base + [str(a) for a in argv]
    if kwargs:
        for k, v in kwargs.items():
            flag = k if str(k).startswith("-") else f"--{k}"
            if v is None:
                continue
            if isinstance(v, bool):
                if v:
                    base.append(flag)
            else:
                base.extend([flag, str(v)])
    return base


def _subprocess_env_extra() -> dict[str, str]:
    extra: dict[str, str] = {}
    try:
        from extensions._core.workflow.workflow_skill_paths import resolve_shared_vasp_config

        cfg = resolve_shared_vasp_config()
        if cfg is not None:
            extra["VASP_SKILLS_CONFIG"] = str(cfg.resolve())
    except Exception:
        logger.debug("Could not resolve VASP_SKILLS_CONFIG for skill subprocess", exc_info=True)
    return extra


def _apply_detach_requirement(
    result: dict[str, Any],
    *,
    skill_name: str,
    require_detach: bool,
) -> dict[str, Any]:
    if not require_detach or result.get("async_envelope"):
        env = result.get("async_envelope")
        if isinstance(env, dict):
            normalized = _normalize_async_envelope_poll_command(env)
            result = {**result, "async_envelope": normalized}
            if normalized.get("status"):
                result["status"] = normalized.get("status")
        return result

    if result.get("success"):
        logger.warning(
            "Skill %r completed synchronously without detach envelope; treating as success",
            skill_name,
        )
        return result

    out = dict(result)
    out["success"] = False
    out["detach_error"] = True
    out["error_kind"] = "submit_failed" if int(out.get("exit_code") or 0) != 0 else "missing_envelope"
    out["error"] = (
        f"Skill {skill_name!r} did not emit a detach envelope (status=submitted). "
        "Inspect stderr, fix argv (--config, --executor, --potcar, etc.), and call run_skill again."
    )
    return out


def _run_subprocess(cmd: list[str], *, cwd: Path, timeout: int, env: dict[str, str] | None = None) -> dict[str, Any]:
    merged_env = {**os.environ, **_subprocess_env_extra(), **(env or {})}
    public_root = str(_skills_repo_root() / "public")
    existing_pp = merged_env.get("PYTHONPATH", "").strip()
    merged_env["PYTHONPATH"] = (
        f"{public_root}{os.pathsep}{existing_pp}" if existing_pp else public_root
    )
    node_outputs = cwd / "outputs"
    node_outputs.mkdir(parents=True, exist_ok=True)
    merged_env.setdefault("POLYMER_BUILD_OUTPUTS", str(node_outputs))
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=merged_env,
    )
    combined = (proc.stdout or "") + ("\n" if proc.stdout and proc.stderr else "") + (proc.stderr or "")
    envelope = resolve_submit_envelope(combined)
    result: dict[str, Any] = {
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "work_dir": str(cwd),
        "success": proc.returncode == 0,
    }
    if envelope:
        envelope = _normalize_async_envelope_poll_command(envelope)
        result["async_envelope"] = envelope
        result["status"] = envelope.get("status")
        result["success"] = False
    summary_path = cwd / "summary.json"
    if summary_path.is_file():
        try:
            result["summary"] = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return result


def run_skill(
    skill_name: str,
    *,
    work_dir: str,
    argv: list[str] | None = None,
    kwargs: dict[str, Any] | None = None,
    command: str | None = None,
    exec_mode: str | None = None,
    sync_timeout: int = 3600,
    require_detach: bool = False,
) -> dict[str, Any]:
    """Run a skill under *work_dir* on the workflow worker."""
    skill_dir = resolve_skill_dir(skill_name)
    cwd = Path(work_dir).resolve()
    cwd.mkdir(parents=True, exist_ok=True)

    if command or exec_mode == "shell":
        if not command:
            raise ValueError("command is required for shell exec_mode")
        shell_cmd = _wrap_shell_with_shared_venv(_rewrite_skill_paths(command))
        cmd = ["/bin/sh", "-c", shell_cmd]
        result = _run_subprocess(cmd, cwd=cwd, timeout=sync_timeout)
        return _apply_detach_requirement(result, skill_name=skill_name, require_detach=require_detach)

    entry = _find_entry_script(skill_dir)
    if entry is None:
        raise FileNotFoundError(
            f"Skill {skill_name!r} has no scripts/run.py or single scripts/*.py entry"
        )

    cmd = _build_argv(entry, argv, kwargs)
    result = _run_subprocess(cmd, cwd=cwd, timeout=sync_timeout)
    return _apply_detach_requirement(result, skill_name=skill_name, require_detach=require_detach)


def skill_result_to_tool_json(result: dict[str, Any]) -> str:
    """Serialize skill result for LLM tool message."""
    return json.dumps(result, ensure_ascii=False, default=str)
