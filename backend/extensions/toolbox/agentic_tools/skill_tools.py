"""
Load LangChain tools from skill directories (tool.py files).
Config tools[].use points to e.g. skill_tools:generate_sam_molecules; we resolve
by scanning the skills root (from config or default) for any skill with tool.py
that defines that attribute.
"""
import importlib.util
import logging
from pathlib import Path
import re
import os

logger = logging.getLogger(__name__)

# name -> (tool_py_path, attr_name); populated on first resolve
_resolve_cache: dict[str, tuple[Path, str]] = {}
# path -> loaded module; avoid re-loading same tool.py for different attrs
_module_cache: dict[Path, object] = {}


def _get_skills_root() -> Path:
    """Skills root: config.skills.get_skills_path() or loader default."""
    try:
        from deerflow.config import get_app_config
        p = get_app_config().skills.get_skills_path()
        if isinstance(p, Path) and p.exists():
            return p
    except Exception:
        pass
    # Fallback: loader default (repo-local skills/)
    from deerflow.skills.loader import get_skills_root_path
    return get_skills_root_path()


def _find_tool_in_skills(tool_name: str) -> tuple[Path, str] | None:
    """Scan skills root (public + custom) for a tool.py that defines tool_name. No hardcoded paths."""
    root = _get_skills_root()
    if not root.exists():
        logger.warning("Skills root does not exist: %s", root)
        return None
    for category in ("public", "custom"):
        cat_path = root / category
        if not cat_path.is_dir():
            continue
        for current_root, dir_names, file_names in os.walk(cat_path):
            # deterministic and skip hidden dirs
            dir_names[:] = sorted(d for d in dir_names if not d.startswith("."))
            if "tool.py" not in file_names:
                continue
            tool_py = Path(current_root) / "tool.py"
            try:
                text = tool_py.read_text(encoding="utf-8", errors="ignore")
                if re.search(rf"^def\s+{re.escape(tool_name)}\s*\(", text, flags=re.MULTILINE):
                    return (tool_py, tool_name)
            except Exception as e:
                logger.debug("Skip %s for %s: %s", tool_py, tool_name, e)
                continue
    return None


def _load_tool_from_file(tool_path: Path, tool_attr: str):
    """Load module from tool_path (cached per path) and return tool_attr."""
    if tool_path in _module_cache:
        mod = _module_cache[tool_path]
    else:
        spec = importlib.util.spec_from_file_location(
            f"skill_tool_{tool_path.parent.name}",
            tool_path,
            submodule_search_locations=[str(tool_path.parent)],
        )
        if spec is None or spec.loader is None:
            raise ValueError(f"Could not load spec for {tool_path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _module_cache[tool_path] = mod
    obj = getattr(mod, tool_attr, None)
    if obj is None:
        raise AttributeError(f"Module {tool_path} has no attribute {tool_attr}")
    return obj


def __getattr__(name: str):
    """Resolve tool by name: find skill with tool.py defining this name under skills root."""
    if name in _resolve_cache:
        path, attr = _resolve_cache[name]
        return _load_tool_from_file(path, attr)
    resolved = _find_tool_in_skills(name)
    if resolved is None:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}. "
            f"No skill under skills root has tool.py defining {name!r}."
        )
    _resolve_cache[name] = resolved
    return _load_tool_from_file(resolved[0], resolved[1])
