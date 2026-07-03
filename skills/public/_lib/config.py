"""Loader for `~/.gaussian_skills/config.yaml` with shared HPC profile support.

Layered model:
  1. ``~/.hpc/profiles.yaml`` — shared HPC credentials registry
     (also read by vasp-skills). See ``_shared-gaussian/hpc-profiles.template.yaml``.
  2. ``~/.gaussian_skills/config.yaml`` — project-local file. Picks one
     profile by name (``profile: <name>``) and adds project-specific
     knobs (defaults, basis, etc).
  3. Project config may override individual HPC fields directly.

Precedence: project override > profile > defaults.
Returns a plain dict (back-compat with existing callers); the merged HPC
fields are written under top-level ``executor``, ``hpc``, ``resources``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

HPC_PROFILES_PATH = Path.home() / ".hpc" / "profiles.yaml"
PROJECT_CONFIG_PATH = Path.home() / ".gaussian_skills" / "config.yaml"

_ENV_VAR_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


class ProfileNotFoundError(KeyError):
    pass


def _expand_env(obj: Any) -> Any:
    if isinstance(obj, str):
        return _ENV_VAR_RE.sub(lambda m: os.environ.get(m.group(1), m.group(0)), obj)
    if isinstance(obj, dict):
        return {k: _expand_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env(x) for x in obj]
    return obj


def _read_yaml(p: Path) -> dict[str, Any]:
    import yaml
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_hpc_profile(
    name: str | None, path: Path = HPC_PROFILES_PATH
) -> tuple[str | None, dict[str, Any]]:
    registry = _read_yaml(path)
    if not registry:
        return None, {}
    profiles = registry.get("profiles", {})
    if name is None:
        name = registry.get("default_profile")
    if not name:
        return None, {}
    if name not in profiles:
        raise ProfileNotFoundError(
            f"profile '{name}' not in {path}. Available: {list(profiles)}"
        )
    return name, _expand_env(profiles[name]) or {}


def _profile_to_blocks(profile: dict[str, Any]) -> dict[str, Any]:
    """Translate the flat profile into gaussian-style executor / hpc / resources."""
    if not profile:
        return {"executor": {"type": "local"}, "hpc": {}, "resources": {}}
    typ = profile.get("type", "local")
    apps = profile.get("apps", {}) or {}
    resources = profile.get("resources", {}) or {}

    executor: dict[str, Any] = {"type": typ}
    if typ == "ssh":
        executor["ssh"] = {
            "host": profile.get("host"),
            "username": profile.get("username") or profile.get("user"),
            "port": profile.get("port", 22),
            "key_path": profile.get("key_path") or profile.get("key_file"),
            "password": profile.get("password"),
        }
    elif typ == "scnet":
        executor["scnet"] = {
            "base_url": profile.get("base_url"),
            "cluster_id": profile.get("cluster_id"),
            "username": profile.get("username"),
            "access_key": profile.get("access_key"),
            "secret_key": profile.get("secret_key"),
        }

    hpc = {
        "work_dir": profile.get("work_root", "/scratch"),
        "scheduler": profile.get("scheduler", "slurm"),
        "modules": profile.get("modules", []),
        "gaussian_command": apps.get("gaussian_cmd", "g16"),
        "gaussian_module": apps.get("gaussian_module"),
    }

    return {
        "executor": executor,
        "hpc": hpc,
        "resources": dict(resources),
    }


def _merge_dicts(base: dict, override: dict) -> dict:
    """Shallow recursive merge — override wins, but inner dicts are merged."""
    out = dict(base)
    for k, v in (override or {}).items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _merge_dicts(out[k], v)
        else:
            out[k] = v
    return out


def load_config(
    path: str | Path | None = None,
    profile: str | None = None,
    hpc_profiles_path: str | Path | None = None,
) -> dict[str, Any]:
    """Load YAML config merged with the HPC profile.

    Returns a dict (preserves back-compat with existing callers).
    Resolved profile name is exposed at ``cfg["profile"]``.
    """
    project_path = (
        Path(path).expanduser()
        if path
        else Path(os.environ.get("GAUSSIAN_SKILLS_CONFIG") or PROJECT_CONFIG_PATH).expanduser()
    )
    project = _read_yaml(project_path)

    profile_name = profile or project.get("profile")
    profiles_path = Path(hpc_profiles_path).expanduser() if hpc_profiles_path else HPC_PROFILES_PATH
    resolved_name, profile_data = _load_hpc_profile(profile_name, profiles_path)

    blocks = _profile_to_blocks(profile_data)
    merged = _merge_dicts(blocks, project)
    merged["profile"] = resolved_name
    return merged
