from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import venv
from pathlib import Path

from deerflow.config.paths import get_paths

logger = logging.getLogger(__name__)

_STATE_FILE_NAME = ".deps-installed.json"
_LOCK_FILE_NAME = ".deps-installed.lock"


def _hash_file(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def _discover_custom_requirements(custom_root: Path) -> list[Path]:
    requirements: list[Path] = []
    for current_root, dir_names, file_names in os.walk(custom_root, followlinks=True):
        dir_names[:] = sorted(name for name in dir_names if not name.startswith("."))
        if "requirements.txt" not in file_names or "SKILL.md" not in file_names:
            continue
        requirements.append(Path(current_root) / "requirements.txt")
    requirements.sort()
    return requirements


def _read_state(state_path: Path) -> dict[str, str]:
    if not state_path.exists():
        return {}
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def _write_state(state_path: Path, state: dict[str, str]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _get_shared_venv_python() -> Path:
    shared_root = get_paths().sandbox_shared_dir()
    return shared_root / ".venv" / "bin" / "python"


def _ensure_pip(python_bin: Path) -> None:
    """uv 等创建的 venv 可能没有 pip；试跑安装依赖前需补齐。"""
    probe = subprocess.run(
        [str(python_bin), "-m", "pip", "--version"],
        capture_output=True,
        text=True,
    )
    if probe.returncode == 0:
        return
    logger.info("Bootstrapping pip in shared sandbox venv (%s)", python_bin)
    bootstrap = subprocess.run(
        [str(python_bin), "-m", "ensurepip", "--upgrade"],
        capture_output=True,
        text=True,
    )
    if bootstrap.returncode != 0:
        detail = ((bootstrap.stdout or "") + (bootstrap.stderr or "")).strip()
        raise RuntimeError(f"Failed to bootstrap pip in shared venv: {detail}")


def _ensure_shared_venv() -> Path:
    python_bin = _get_shared_venv_python()
    if not python_bin.exists():
        venv_dir = python_bin.parent.parent
        logger.info("Creating shared sandbox venv at %s", venv_dir)
        # symlinks=True 必需：uv 安装的 CPython 依赖 @rpath/libpython3.12.dylib，默认的 --copies 模式
        # 只拷贝 python 可执行文件而不拷贝该 dylib，导致沙盒解释器一启动就 dyld 崩溃
        # (Library not loaded: @rpath/libpython3.12.dylib)。symlinks 让解释器指回原 Python 目录，dylib 可解析。
        venv.EnvBuilder(with_pip=True, symlinks=True).create(str(venv_dir))
    _ensure_pip(python_bin)
    return python_bin


def ensure_shared_skill_venv() -> Path:
    """Ensure the shared sandbox venv exists and return its python path."""
    return _ensure_shared_venv()


def _install_requirements_file(requirements_file: Path, python_bin: Path) -> None:
    logger.info("Installing custom skill dependencies from %s into %s", requirements_file, python_bin)
    subprocess.run(
        [str(python_bin), "-m", "pip", "install", "-r", str(requirements_file)],
        check=True,
    )


def ensure_custom_skill_dependencies(skills_root: Path) -> None:
    """Install `skills/custom/**/requirements.txt` into sandbox shared venv.

    Uses a hash state file to avoid reinstalling unchanged requirements files.
    """
    custom_root = skills_root / "custom"
    if not custom_root.exists() or not custom_root.is_dir():
        return

    state_path = custom_root / _STATE_FILE_NAME
    lock_path = custom_root / _LOCK_FILE_NAME

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        try:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        except Exception:
            # Best effort lock; continue without failing.
            pass

        state = _read_state(state_path)
        current_requirements = _discover_custom_requirements(custom_root)
        next_state: dict[str, str] = {}

        python_bin = _ensure_shared_venv()

        for req_file in current_requirements:
            file_hash = _hash_file(req_file)
            key = str(req_file.relative_to(custom_root))
            next_state[key] = file_hash
            if state.get(key) == file_hash:
                continue

            _install_requirements_file(req_file, python_bin)

        _write_state(state_path, next_state)
