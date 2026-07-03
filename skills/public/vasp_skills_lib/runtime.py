"""Shared compute-runtime status reader/writer.

This module is intentionally software-neutral. It stores minimal execution
state under ``work_dir/.calc_runtime`` so VASP / Gaussian / future backends can
share the same status schema.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUNTIME_DIRNAME = ".calc_runtime"
PROGRESS_FILE = "progress.json"
EVENTS_FILE = "events.jsonl"
JOB_FILE = "job.json"
HISTORY_DIR = "history"


class RuntimeState:
    QUEUED = "queued"
    RUNNING = "running"
    CORRECTING = "correcting"
    FETCHING = "fetching"
    PARSING = "parsing"
    FINISHED = "finished"
    FAILED = "failed"



def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()



def runtime_dir(work_dir: Path) -> Path:
    path = Path(work_dir) / RUNTIME_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path



def history_dir(work_dir: Path) -> Path:
    path = runtime_dir(work_dir) / HISTORY_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path



def write_progress(work_dir: Path, payload: dict[str, Any]) -> Path:
    path = runtime_dir(work_dir) / PROGRESS_FILE
    current = read_progress(work_dir)
    merged = {**current, **payload}
    merged.setdefault("started_at", _now_iso())
    merged["updated_at"] = _now_iso()
    path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    return path



def write_job(work_dir: Path, payload: dict[str, Any]) -> Path:
    path = runtime_dir(work_dir) / JOB_FILE
    current = read_job(work_dir)
    merged = {**current, **payload, "updated_at": _now_iso()}
    path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    return path



def append_event(work_dir: Path, event: dict[str, Any]) -> Path:
    path = runtime_dir(work_dir) / EVENTS_FILE
    row = {"ts": _now_iso(), **event}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path



def read_progress(work_dir: Path) -> dict[str, Any]:
    path = Path(work_dir) / RUNTIME_DIRNAME / PROGRESS_FILE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}



def read_job(work_dir: Path) -> dict[str, Any]:
    path = Path(work_dir) / RUNTIME_DIRNAME / JOB_FILE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}



def read_events(work_dir: Path, limit: int = 20) -> list[dict[str, Any]]:
    path = Path(work_dir) / RUNTIME_DIRNAME / EVENTS_FILE
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        return []
    return rows[-limit:]



def read_log_tail(work_dir: Path, names: list[str], max_lines: int = 20) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in names:
        path = Path(work_dir) / name
        if not path.exists() or path.is_dir():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        out[name] = "\n".join(lines[-max_lines:])
    return out
