from __future__ import annotations

import ast
import hashlib
import logging
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from deerflow.skills.dependencies import ensure_shared_skill_venv

logger = logging.getLogger(__name__)

PIP_INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple"
_CONFLICT_MARKERS = (
    "resolutionimpossible",
    "conflict",
    "cannot install",
    "has requirement",
    "incompatible",
)


@dataclass
class DepsInstallResult:
    ok: bool
    deps_error: bool = False
    message: str = ""
    detail: str = ""


def _is_conflict_output(text: str, exit_code: int) -> bool:
    if exit_code == 0:
        return False
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _CONFLICT_MARKERS)


def _requirements_hash(requirements_text: str) -> str:
    normalized = "\n".join(line.strip() for line in requirements_text.splitlines() if line.strip())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _state_path(tool_id: str) -> Path:
    from deerflow.config.paths import get_paths

    root = get_paths().sandbox_shared_dir() / "workflow-tools-deps"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{tool_id}.hash"


def ensure_tool_requirements(tool_id: str, requirements_text: str | None) -> DepsInstallResult:
    """Install tool requirements into shared venv; dry-run first; abort on conflict."""
    ensure_shared_skill_venv()
    python_bin = ensure_shared_skill_venv()
    req = (requirements_text or "").strip()
    if not req:
        return DepsInstallResult(ok=True)

    req_hash = _requirements_hash(req)
    state_file = _state_path(tool_id)
    if state_file.exists() and state_file.read_text(encoding="utf-8").strip() == req_hash:
        return DepsInstallResult(ok=True)

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tmp:
        tmp.write(req)
        req_path = tmp.name

    try:
        dry = subprocess.run(
            [
                str(python_bin),
                "-m",
                "pip",
                "install",
                "--dry-run",
                "-r",
                req_path,
                "-i",
                PIP_INDEX,
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        combined = (dry.stdout or "") + (dry.stderr or "")
        if _is_conflict_output(combined, dry.returncode):
            return DepsInstallResult(
                ok=False,
                deps_error=True,
                message="依赖冲突，已取消安装",
                detail=combined.strip()[:4000],
            )
        if dry.returncode != 0:
            return DepsInstallResult(
                ok=False,
                deps_error=False,
                message="依赖预检查失败",
                detail=combined.strip()[:4000],
            )

        install = subprocess.run(
            [
                str(python_bin),
                "-m",
                "pip",
                "install",
                "-r",
                req_path,
                "-i",
                PIP_INDEX,
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        combined = (install.stdout or "") + (install.stderr or "")
        if install.returncode != 0:
            conflict = _is_conflict_output(combined, install.returncode)
            return DepsInstallResult(
                ok=False,
                deps_error=conflict,
                message="依赖冲突，已取消安装" if conflict else "依赖安装失败",
                detail=combined.strip()[:4000],
            )

        state_file.write_text(req_hash, encoding="utf-8")
        return DepsInstallResult(ok=True)
    finally:
        Path(req_path).unlink(missing_ok=True)


# Common import name → PyPI package name
_MODULE_TO_PIP: dict[str, str] = {
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv",
    # PyPI 上分子模拟包名为 radonpy-pypi，勿装同名的 radon 检测仪包 radonpy
    "radonpy": "radonpy-pypi[lammps]",
}

# Already expected in the shared workflow venv; skip auto-install
_SKIP_MODULES = frozenset(
    {
        "langchain_core",
        "langchain",
        "pydantic",
        "typing",
        "typing_extensions",
        "asyncio",
        "json",
        "os",
        "sys",
        "pathlib",
        "re",
        "datetime",
        "functools",
        "itertools",
        "collections",
        "dataclasses",
        "enum",
        "uuid",
        "logging",
        "inspect",
        "importlib",
    }
)


def extract_import_packages(script: str) -> list[str]:
    """Parse script imports and return deduplicated PyPI package names to install."""
    try:
        tree = ast.parse(script)
    except SyntaxError:
        return []

    module_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root:
                    module_roots.add(root)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                if root:
                    module_roots.add(root)

    stdlib = getattr(sys, "stdlib_module_names", frozenset())
    pip_names: list[str] = []
    seen: set[str] = set()
    for mod in sorted(module_roots):
        if mod in stdlib or mod in _SKIP_MODULES:
            continue
        pkg = _MODULE_TO_PIP.get(mod, mod)
        if pkg not in seen:
            seen.add(pkg)
            pip_names.append(pkg)
    return pip_names


def ensure_script_imports(tool_id: str, script: str | None) -> DepsInstallResult:
    """Install third-party packages inferred from script import statements."""
    packages = extract_import_packages(script or "")
    if not packages:
        return DepsInstallResult(ok=True)

    for pkg in packages:
        result = ensure_single_package(pkg)
        if not result.ok:
            result.message = f"{result.message} (包: {pkg})"
            return result
    return DepsInstallResult(ok=True)


def ensure_single_package(package_name: str) -> DepsInstallResult:
    """Install one package (ModuleNotFoundError recovery) with dry-run conflict check."""
    pkg = package_name.strip()
    if not pkg or not re.match(r"^[A-Za-z0-9_.\-\[\]=,]+$", pkg):
        return DepsInstallResult(ok=False, message="无效的包名", detail=package_name)

    python_bin = ensure_shared_skill_venv()
    dry = subprocess.run(
        [str(python_bin), "-m", "pip", "install", "--dry-run", pkg, "-i", PIP_INDEX],
        capture_output=True,
        text=True,
        timeout=120,
    )
    combined = (dry.stdout or "") + (dry.stderr or "")
    if _is_conflict_output(combined, dry.returncode):
        return DepsInstallResult(
            ok=False,
            deps_error=True,
            message="依赖冲突，已取消安装",
            detail=combined.strip()[:4000],
        )
    if dry.returncode != 0:
        return DepsInstallResult(ok=False, message="依赖预检查失败", detail=combined.strip()[:4000])

    install = subprocess.run(
        [str(python_bin), "-m", "pip", "install", pkg, "-i", PIP_INDEX],
        capture_output=True,
        text=True,
        timeout=300,
    )
    combined = (install.stdout or "") + (install.stderr or "")
    if install.returncode != 0:
        conflict = _is_conflict_output(combined, install.returncode)
        return DepsInstallResult(
            ok=False,
            deps_error=conflict,
            message="依赖冲突，已取消安装" if conflict else "依赖安装失败",
            detail=combined.strip()[:4000],
        )
    return DepsInstallResult(ok=True)
