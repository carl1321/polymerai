"""Load the vasp-skills config.

Layered model (introduced 2026-04):
  1. ``/mnt/skills/public/_shared-vasp/profiles.yaml`` (fallback:
     ``skills/public/_shared-vasp/profiles.yaml``) — shared HPC credentials
     registry (a dict of named profiles).
  2. ``/mnt/skills/public/_shared-vasp/config.yaml`` (fallback:
     ``skills/public/_shared-vasp/config.yaml``) — project-local file.
     Picks one profile
     by name (``profile: <name>``) and adds project-specific knobs
     (handlers, potcar, ...).
  3. Project config may override individual HPC fields by setting ``ssh:``
     or ``scnet:`` directly — useful for ad-hoc debugging.

Precedence for the executor block: project override > profile > defaults.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


_SANDBOX_SHARED_DIR = Path("/mnt/skills/public/_shared-vasp")
_REPO_SHARED_DIR = Path(__file__).resolve().parents[1] / "_shared-vasp"


def _resolve_default_path(filename: str) -> Path:
    sandbox_path = _SANDBOX_SHARED_DIR / filename
    if sandbox_path.exists():
        return sandbox_path
    return _REPO_SHARED_DIR / filename


HPC_PROFILES_PATH = _resolve_default_path("profiles.yaml")
PROJECT_CONFIG_PATH = _resolve_default_path("config.yaml")


@dataclass
class Config:
    executor: str = "local"
    profile_name: str | None = None
    local: dict[str, Any] = field(default_factory=dict)
    ssh: dict[str, Any] = field(default_factory=dict)
    scnet: dict[str, Any] = field(default_factory=dict)
    handlers: dict[str, Any] = field(default_factory=lambda: {"enabled": True, "max_errors": 5})
    potcar: dict[str, Any] = field(default_factory=lambda: {"backend": "vasp-potcar", "functional": "PBE"})
    raw: dict[str, Any] = field(default_factory=dict)


class ProfileNotFoundError(KeyError):
    """The project asked for a profile that does not exist in profiles.yaml."""


_ENV_VAR_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def _expand_env(obj: Any) -> Any:
    """Recursively expand ${ENV_VAR} placeholders in strings (for API keys)."""
    if isinstance(obj, str):
        return _ENV_VAR_RE.sub(lambda m: os.environ.get(m.group(1), m.group(0)), obj)
    if isinstance(obj, dict):
        return {k: _expand_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env(x) for x in obj]
    return obj


def _read_yaml(p: Path) -> dict[str, Any]:
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_hpc_profile(name: str | None, path: Path = HPC_PROFILES_PATH) -> tuple[str | None, dict[str, Any]]:
    """Return (resolved_name, profile_dict). Empty dict if the registry is missing."""
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


def _profile_to_executor_blocks(profile: dict[str, Any]) -> dict[str, Any]:
    """Translate a flat profile dict into the legacy ssh:/scnet:/local: layout."""
    if not profile:
        return {"executor": "local", "local": {}, "ssh": {}, "scnet": {}}
    typ = profile.get("type", "local")
    apps = profile.get("apps", {}) or {}
    resources = profile.get("resources", {}) or {}
    blocks: dict[str, Any] = {"executor": typ, "local": {}, "ssh": {}, "scnet": {}}

    if typ == "local":
        blocks["local"] = {
            "vasp_cmd": apps.get("vasp_cmd", "mpirun -np 4 vasp_std"),
            "scratch_dir": profile.get("scratch_dir", "/tmp/vasp_skills"),
        }
    elif typ == "ssh":
        blocks["ssh"] = {
            "host": profile.get("host"),
            "port": profile.get("port", 22),
            "user": profile.get("username") or profile.get("user"),
            "key_file": profile.get("key_path") or profile.get("key_file"),
            "password": profile.get("password"),
            "remote_root": profile.get("work_root", "~/vasp_skills_runs"),
            "vasp_cmd": apps.get("vasp_cmd", "mpirun vasp_std"),
            "scheduler": profile.get("scheduler", "slurm"),
            "modules": profile.get("modules", []),
            "partition": resources.get("partition", "normal"),
            "nodes": resources.get("nodes", 1),
            "ntasks_per_node": resources.get("ntasks_per_node", 32),
            "walltime": resources.get("walltime", "24:00:00"),
        }
    elif typ == "scnet":
        blocks["scnet"] = {
            "api_base": profile.get("base_url"),
            "ingress_url": profile.get("ingress_url") or profile.get("base_url"),
            "hpc_url": profile.get("hpc_url"),
            "efile_url": profile.get("efile_url"),
            "cluster_id": profile.get("cluster_id"),
            "cluster_name": profile.get("cluster_name"),
            "username": profile.get("username"),
            "access_key": profile.get("access_key"),
            "secret_key": profile.get("secret_key"),
            "token": profile.get("token"),
            "remote_root": profile.get("work_root", "/public/home"),
            "scheduler": profile.get("scheduler", "slurm"),
            "modules": profile.get("modules", []),
            "partition": resources.get("partition", "kshcnormal"),
            "ntasks_per_node": resources.get("ntasks_per_node"),
            "queue": resources.get("queue") or resources.get("partition", "normal"),
            "nodes": resources.get("nodes", 1),
            "cores": resources.get("cores") or resources.get("ntasks_per_node", 32),
            "walltime": resources.get("walltime", "24:00:00"),
            "vasp_cmd": apps.get("vasp_cmd", "mpirun vasp_std"),
            "poll_interval": profile.get("poll_interval", 60),
        }
    return blocks


def load_config(
    path: str | Path | None = None,
    profile: str | None = None,
    hpc_profiles_path: str | Path | None = None,
) -> Config:
    """Load merged config.

    Args:
        path: project config file. Defaults to ``$VASP_SKILLS_CONFIG`` or
            resolved default config path.
        profile: override the profile name selected by the project config.
        hpc_profiles_path: override resolved default profiles.yaml location.
    """
    project_path = (
        Path(path).expanduser()
        if path
        else Path(os.environ.get("VASP_SKILLS_CONFIG") or PROJECT_CONFIG_PATH).expanduser()
    )
    project = _read_yaml(project_path)

    profile_name = profile or project.get("profile")
    profiles_path = Path(hpc_profiles_path).expanduser() if hpc_profiles_path else HPC_PROFILES_PATH
    resolved_name, profile_data = _load_hpc_profile(profile_name, profiles_path)

    blocks = _profile_to_executor_blocks(profile_data)

    executor = project.get("executor", blocks["executor"])
    if executor is None:
        executor = blocks["executor"]

    cfg = Config(
        executor=executor,
        profile_name=resolved_name,
        local={**blocks["local"], **(project.get("local") or {})},
        ssh={**blocks["ssh"], **(project.get("ssh") or {})},
        scnet={**blocks["scnet"], **(project.get("scnet") or {})},
        handlers=project.get("handlers", {"enabled": True, "max_errors": 5}),
        potcar=project.get("potcar", {"backend": "vasp-potcar", "functional": "PBE"}),
        raw=project,
    )
    return cfg
