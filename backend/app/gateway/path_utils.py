"""Shared path resolution for thread virtual paths (e.g. mnt/user-data/outputs/...)."""

from pathlib import Path
from typing import cast

from fastapi import HTTPException, Request

from deerflow.config.paths import get_paths
from deerflow.runtime.user_context import resolve_fs_user_id_for_thread

_FS_USER_ID_UNSET = object()


def resolve_thread_virtual_path(
    thread_id: str,
    virtual_path: str,
    *,
    fs_user_id: str | None | object = _FS_USER_ID_UNSET,
) -> Path:
    """Resolve a virtual path to the actual filesystem path under thread user-data.

    If ``fs_user_id`` is omitted, uses :func:`resolve_fs_user_id_for_thread`.
    Pass ``fs_user_id=None`` for legacy rows whose data lives under
    ``{base}/threads/{thread_id}/`` (no per-user prefix).

    Raises:
        HTTPException: If the path is invalid or outside allowed directories.
    """
    try:
        if fs_user_id is _FS_USER_ID_UNSET:
            effective_user_id = resolve_fs_user_id_for_thread()
        else:
            effective_user_id = cast(str | None, fs_user_id)
        return get_paths().resolve_virtual_path(thread_id, virtual_path, user_id=effective_user_id)
    except ValueError as e:
        status = 403 if "traversal" in str(e) else 400
        raise HTTPException(status_code=status, detail=str(e))


def resolve_artifact_host_path(
    thread_id: str,
    virtual_path: str,
    *,
    fs_user_id: str | None | object = _FS_USER_ID_UNSET,
) -> Path:
    """Resolve artifact virtual path, trying per-user then legacy thread layouts."""
    tried: list[str] = []
    candidates: list[Path] = []

    def _add(user_id: str | None) -> None:
        try:
            p = get_paths().resolve_virtual_path(thread_id, virtual_path, user_id=user_id)
        except ValueError:
            return
        candidates.append(p)
        tried.append(str(p))

    if fs_user_id is _FS_USER_ID_UNSET:
        effective = resolve_fs_user_id_for_thread()
    else:
        effective = cast(str | None, fs_user_id)

    if effective is not None:
        _add(effective)
    _add(None)

    stripped = virtual_path.lstrip("/")
    prefix = "mnt/user-data/"
    if stripped.startswith(prefix) and "outputs/" in stripped:
        fname = Path(stripped).name
        host_shared = Path("/mnt/user-data/outputs") / fname
        if host_shared.is_file():
            candidates.append(host_shared.resolve())
            tried.append(str(host_shared.resolve()))

    for path in candidates:
        if path.is_file():
            return path

    raise HTTPException(
        status_code=404,
        detail={
            "message": f"Artifact not found: {virtual_path}",
            "thread_id": thread_id,
            "searched": tried,
            "hint": "Artifacts are served from this thread's user-data/outputs on the gateway host (DEER_FLOW_HOME), not arbitrary server paths.",
        },
    )


async def resolve_thread_path_user_id(thread_id: str, request: Request) -> str | None:
    """Resolve filesystem owner id for *thread_id* from metadata, else request context."""
    try:
        app = request.app
    except KeyError:
        return resolve_fs_user_id_for_thread()
    store = getattr(app.state, "thread_store", None)
    if store is None:
        return resolve_fs_user_id_for_thread()
    try:
        rec = await store.get(thread_id, user_id=None)
    except Exception:
        return resolve_fs_user_id_for_thread()
    if rec is None:
        return resolve_fs_user_id_for_thread()
    uid = rec.get("user_id")
    if uid is None:
        return None
    return str(uid)
