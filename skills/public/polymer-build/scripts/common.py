from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def default_outputs_dir(work_dir: Path) -> Path:
    env = os.environ.get("POLYMER_BUILD_OUTPUTS", "").strip()
    if env:
        p = Path(env)
        p.mkdir(parents=True, exist_ok=True)
        return p
    out = work_dir / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    # Only use sandbox-mounted /mnt/user-data/outputs (per-thread), not a host-global directory.
    if os.environ.get("DEERFLOW_SANDBOX") == "1":
        fallback = Path("/mnt/user-data/outputs")
        if fallback.is_dir():
            return fallback
    return out


def manifest_path(work_dir: Path) -> Path:
    return work_dir / "manifest.json"


def load_manifest(work_dir: Path) -> dict[str, Any]:
    p = manifest_path(work_dir)
    if not p.is_file():
        return {"work_dir": str(work_dir.resolve())}
    return json.loads(p.read_text(encoding="utf-8"))


def save_manifest(work_dir: Path, data: dict[str, Any]) -> None:
    base = load_manifest(work_dir)
    base.update(data)
    base["work_dir"] = str(work_dir.resolve())
    manifest_path(work_dir).write_text(json.dumps(base, indent=2, sort_keys=True), encoding="utf-8")


def skill_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def repo_skills_public() -> Path:
    return skill_dir().parent

