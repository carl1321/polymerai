"""One-time migration: move legacy thread dirs and memory into per-user layout.

Usage:
    PYTHONPATH=. python scripts/migrate_user_isolation.py [--dry-run]

The script is idempotent — re-running it after a successful migration is a no-op.
"""

import argparse
import json
import logging
import shutil
from pathlib import Path
from typing import Any

from deerflow.config import get_app_config
from deerflow.config.app_config import AppConfig
from deerflow.config.paths import Paths, get_paths

logger = logging.getLogger(__name__)


def migrate_thread_dirs(
    paths: Paths,
    thread_owner_map: dict[str, str],
    *,
    batch_size: int | None = None,
    dry_run: bool = False,
) -> list[dict]:
    """Move legacy thread directories into per-user layout.

    Args:
        paths: Paths instance.
        thread_owner_map: Mapping of thread_id -> user_id from threads_meta table.
        dry_run: If True, only log what would happen.

    Returns:
        List of migration report entries.
    """
    report: list[dict] = []
    legacy_threads = paths.base_dir / "threads"
    if not legacy_threads.exists():
        logger.info("No legacy threads directory found — nothing to migrate.")
        return report

    processed = 0
    for thread_dir in sorted(legacy_threads.iterdir()):
        if not thread_dir.is_dir():
            continue
        if batch_size is not None and processed >= batch_size:
            break
        processed += 1
        thread_id = thread_dir.name
        user_id = thread_owner_map.get(thread_id)
        entry = {"thread_id": thread_id, "user_id": user_id, "action": ""}
        if not user_id:
            entry["action"] = "missing_owner"
            logger.warning("Missing owner for thread %s; skipped migration", thread_id)
            report.append(entry)
            continue
        dest = paths.user_thread_dir(user_id, thread_id)

        if dest.exists():
            conflicts_dir = paths.base_dir / "migration-conflicts" / thread_id
            entry["action"] = f"conflict -> {conflicts_dir}"
            if not dry_run:
                conflicts_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(thread_dir), str(conflicts_dir))
            logger.warning("Conflict for thread %s: moved to %s", thread_id, conflicts_dir)
        else:
            entry["action"] = f"moved -> {dest}"
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(thread_dir), str(dest))
            logger.info("Migrated thread %s -> user %s", thread_id, user_id)

        report.append(entry)

    # Clean up empty legacy threads dir
    if not dry_run and legacy_threads.exists() and not any(legacy_threads.iterdir()):
        legacy_threads.rmdir()

    return report


def _list_legacy_thread_ids(paths: Paths, *, batch_size: int | None = None) -> list[str]:
    legacy_threads = paths.base_dir / "threads"
    if not legacy_threads.exists():
        return []
    thread_ids: list[str] = []
    for thread_dir in sorted(legacy_threads.iterdir()):
        if not thread_dir.is_dir():
            continue
        thread_ids.append(thread_dir.name)
        if batch_size is not None and len(thread_ids) >= batch_size:
            break
    return thread_ids


def _list_user_thread_ids(paths: Paths, user_id: str) -> list[str]:
    threads_dir = paths.user_dir(user_id) / "threads"
    if not threads_dir.exists():
        return []
    return [d.name for d in sorted(threads_dir.iterdir()) if d.is_dir()]


def _apply_fallback_owner(
    thread_ids: list[str],
    owner_map: dict[str, str],
    *,
    fallback_user_id: str | None,
) -> tuple[dict[str, str], list[str]]:
    resolved = dict(owner_map)
    fallback_applied: list[str] = []
    if not fallback_user_id:
        return resolved, fallback_applied
    for thread_id in thread_ids:
        if not resolved.get(thread_id):
            resolved[thread_id] = fallback_user_id
            fallback_applied.append(thread_id)
    return resolved, fallback_applied


def _upsert_threads_meta_owner(
    paths: Paths,
    owner_map: dict[str, str],
    *,
    db_path_arg: str | None = None,
    dry_run: bool = False,
) -> tuple[int, Path | None]:
    """Upsert thread_id -> user_id into sqlite threads_meta."""
    import sqlite3
    from datetime import UTC, datetime

    db_path = _resolve_db_path(paths, db_path_arg=db_path_arg)
    if db_path is None:
        logger.warning("Skip threads_meta upsert: sqlite DB not found.")
        return 0, None

    if not owner_map:
        return 0, db_path

    if dry_run:
        logger.info("Dry-run: would upsert %d ownership rows into %s", len(owner_map), db_path)
        return len(owner_map), db_path

    now = datetime.now(UTC).isoformat()
    conn = sqlite3.connect(str(db_path))
    try:
        # Compatible minimal table for environments where app persistence table is absent.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS threads_meta (
              thread_id TEXT PRIMARY KEY,
              user_id TEXT,
              created_at TEXT,
              updated_at TEXT
            )
            """
        )
        conn.commit()

        cols = {row[1] for row in conn.execute("PRAGMA table_info(threads_meta)").fetchall()}
        insert_cols = ["thread_id", "user_id"]
        if "created_at" in cols:
            insert_cols.append("created_at")
        if "updated_at" in cols:
            insert_cols.append("updated_at")

        placeholders = ", ".join("?" for _ in insert_cols)
        assignments = ["user_id=excluded.user_id"]
        if "updated_at" in cols:
            assignments.append("updated_at=excluded.updated_at")
        sql = (
            f"INSERT INTO threads_meta ({', '.join(insert_cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT(thread_id) DO UPDATE SET {', '.join(assignments)}"
        )

        upserted = 0
        for thread_id, user_id in owner_map.items():
            row: list[Any] = [thread_id, user_id]
            if "created_at" in cols:
                row.append(now)
            if "updated_at" in cols:
                row.append(now)
            conn.execute(sql, row)
            upserted += 1
        conn.commit()
        return upserted, db_path
    finally:
        conn.close()


def _build_owner_map_from_checkpoints_db(paths: Paths, *, db_path_arg: str | None = None) -> dict[str, str]:
    """Extract thread owner mapping from checkpoints.metadata.user_id."""
    import json as _json
    import sqlite3

    db_path = _resolve_db_path(paths, db_path_arg=db_path_arg)
    if db_path is None:
        return {}

    conn = sqlite3.connect(str(db_path))
    owner_map: dict[str, str] = {}
    try:
        cursor = conn.execute("SELECT thread_id, metadata FROM checkpoints")
        for thread_id, metadata in cursor.fetchall():
            if not thread_id or thread_id in owner_map:
                continue
            try:
                meta_obj = _json.loads(metadata)
            except Exception:
                continue
            owner = meta_obj.get("user_id")
            if isinstance(owner, str) and owner.strip():
                owner_map[thread_id] = owner.strip()
    except sqlite3.OperationalError as e:
        logger.warning("Failed to scan checkpoints table: %s", e)
    finally:
        conn.close()
    return owner_map


def reconcile_migrated_thread_dirs(
    paths: Paths,
    owner_map: dict[str, str],
    *,
    dry_run: bool = False,
) -> list[dict]:
    """Move already-migrated threads from default user bucket to actual owner bucket."""
    report: list[dict] = []
    default_threads_dir = paths.user_dir("default") / "threads"
    if not default_threads_dir.exists():
        return report

    for thread_dir in sorted(default_threads_dir.iterdir()):
        if not thread_dir.is_dir():
            continue
        thread_id = thread_dir.name
        target_user = owner_map.get(thread_id)
        if not target_user or target_user == "default":
            continue
        dest = paths.user_thread_dir(target_user, thread_id)
        entry = {"thread_id": thread_id, "user_id": target_user, "action": ""}
        if dest.exists():
            conflicts_dir = paths.base_dir / "migration-conflicts" / thread_id
            entry["action"] = f"conflict -> {conflicts_dir}"
            if not dry_run:
                conflicts_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(thread_dir), str(conflicts_dir))
        else:
            entry["action"] = f"moved -> {dest}"
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(thread_dir), str(dest))
        report.append(entry)

    if not dry_run and default_threads_dir.exists() and not any(default_threads_dir.iterdir()):
        default_threads_dir.rmdir()
    return report


def migrate_agents(
    paths: Paths,
    user_id: str = "default",
    *,
    dry_run: bool = False,
) -> list[dict]:
    """Move legacy custom-agent directories into per-user layout."""
    report: list[dict] = []
    legacy_agents = paths.agents_dir
    if not legacy_agents.exists():
        logger.info("No legacy agents directory found — nothing to migrate.")
        return report

    for agent_dir in sorted(legacy_agents.iterdir()):
        if not agent_dir.is_dir():
            continue
        agent_name = agent_dir.name
        dest = paths.user_agent_dir(user_id, agent_name)
        entry = {"agent": agent_name, "user_id": user_id, "action": ""}
        if dest.exists():
            conflicts_dir = paths.base_dir / "migration-conflicts" / "agents" / agent_name
            entry["action"] = f"conflict -> {conflicts_dir}"
            if not dry_run:
                conflicts_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(agent_dir), str(conflicts_dir))
            logger.warning("Conflict for agent %s: moved legacy copy to %s", agent_name, conflicts_dir)
        else:
            entry["action"] = f"moved -> {dest}"
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(agent_dir), str(dest))
            logger.info("Migrated agent %s -> user %s", agent_name, user_id)
        report.append(entry)

    if not dry_run and legacy_agents.exists() and not any(legacy_agents.iterdir()):
        legacy_agents.rmdir()
    return report


def migrate_memory(
    paths: Paths,
    user_id: str = "default",
    *,
    dry_run: bool = False,
) -> None:
    """Move legacy global memory.json into per-user layout.

    Args:
        paths: Paths instance.
        user_id: Target user to receive the legacy memory.
        dry_run: If True, only log.
    """
    legacy_mem = paths.base_dir / "memory.json"
    if not legacy_mem.exists():
        logger.info("No legacy memory.json found — nothing to migrate.")
        return

    dest = paths.user_memory_file(user_id)
    if dest.exists():
        legacy_backup = paths.base_dir / "memory.legacy.json"
        logger.warning("Destination %s exists; renaming legacy to %s", dest, legacy_backup)
        if not dry_run:
            legacy_mem.rename(legacy_backup)
        return

    logger.info("Migrating memory.json -> %s", dest)
    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy_mem), str(dest))


def _resolve_db_path(paths: Paths, *, db_path_arg: str | None = None) -> Path | None:
    """Resolve sqlite DB path for reading threads_meta ownership."""
    backend_dir = Path(__file__).resolve().parents[1]
    try:
        config_dir = AppConfig.resolve_config_path().parent
    except Exception:
        config_dir = backend_dir
    candidates: list[Path] = []
    if db_path_arg:
        candidates.append(Path(db_path_arg).expanduser())
    else:
        try:
            app_config = get_app_config()
            checkpointer = app_config.checkpointer
            if checkpointer and checkpointer.type == "sqlite" and checkpointer.connection_string:
                checkpointer_path = Path(checkpointer.connection_string).expanduser()
                if not checkpointer_path.is_absolute():
                    checkpointer_path = config_dir / checkpointer_path
                candidates.append(checkpointer_path)
        except Exception as exc:
            logger.warning("Failed to read checkpointer config: %s", exc)

    # Legacy and current-known sqlite locations (fallbacks)
    candidates.extend(
        [
            paths.base_dir / "checkpoints.db",
            paths.base_dir / "deer-flow.db",
            paths.base_dir / "data" / "deerflow.db",
            backend_dir / "checkpoints.db",
        ]
    )

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists():
            return resolved

    logger.info("No database found in candidates: %s", ", ".join(str(p) for p in seen))
    return None


def _build_owner_map_from_db(paths: Paths, *, db_path_arg: str | None = None) -> dict[str, str]:
    """Query threads_meta table for thread_id -> user_id mapping.

    Uses raw sqlite3 to avoid async dependencies.
    """
    import sqlite3

    db_path = _resolve_db_path(paths, db_path_arg=db_path_arg)
    if db_path is None:
        return {}

    logger.info("Using ownership database: %s", db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute("SELECT thread_id, user_id FROM threads_meta WHERE user_id IS NOT NULL")
        return {row[0]: row[1] for row in cursor.fetchall()}
    except sqlite3.OperationalError as e:
        logger.warning("Failed to query threads_meta: %s", e)
        return {}
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate DeerFlow data to per-user layout")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without making changes")
    parser.add_argument("--batch-size", type=int, default=None, help="Max number of legacy thread directories to process")
    parser.add_argument("--mapping-log", type=str, default=None, help="Write migration mapping log as JSONL")
    parser.add_argument("--db-path", type=str, default=None, help="SQLite DB path for threads_meta ownership lookup")
    parser.add_argument("--fallback-user-id", type=str, default=None, help="Fallback owner for threads with missing owner")
    parser.add_argument(
        "--user-id",
        default=None,
        metavar="USER_ID",
        help="User ID for legacy memory/agents migration (defaults to --fallback-user-id or 'default')",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    paths = get_paths()
    logger.info("Base directory: %s", paths.base_dir)
    logger.info("Dry run: %s", args.dry_run)

    owner_map = _build_owner_map_from_db(paths, db_path_arg=args.db_path)
    checkpoint_owner_map = _build_owner_map_from_checkpoints_db(paths, db_path_arg=args.db_path)
    if checkpoint_owner_map:
        logger.info("Found %d ownership records in checkpoints metadata", len(checkpoint_owner_map))
        owner_map = {**checkpoint_owner_map, **owner_map}
    logger.info("Found %d total ownership records", len(owner_map))

    legacy_thread_ids = _list_legacy_thread_ids(paths, batch_size=args.batch_size)
    candidate_thread_ids = set(legacy_thread_ids)
    candidate_thread_ids.update(_list_user_thread_ids(paths, "default"))
    resolved_owner_map, fallback_applied = _apply_fallback_owner(
        sorted(candidate_thread_ids),
        owner_map,
        fallback_user_id=args.fallback_user_id,
    )
    if fallback_applied:
        logger.info("Applied fallback owner '%s' to %d threads", args.fallback_user_id, len(fallback_applied))

    upserted_rows, db_path = _upsert_threads_meta_owner(
        paths,
        {tid: uid for tid, uid in resolved_owner_map.items() if tid in candidate_thread_ids and uid},
        db_path_arg=args.db_path,
        dry_run=args.dry_run,
    )
    if db_path is not None:
        logger.info("threads_meta ownership upsert rows: %d (db=%s)", upserted_rows, db_path)

    report = migrate_thread_dirs(paths, resolved_owner_map, batch_size=args.batch_size, dry_run=args.dry_run)
    reconcile_report = reconcile_migrated_thread_dirs(paths, resolved_owner_map, dry_run=args.dry_run)
    report.extend(reconcile_report)
    claim_user_id = args.user_id or args.fallback_user_id or "default"
    migrate_memory(paths, user_id=claim_user_id, dry_run=args.dry_run)
    agent_report = migrate_agents(paths, user_id=claim_user_id, dry_run=args.dry_run)

    if report:
        logger.info("Migration report:")
        for entry in report:
            logger.info("  thread=%s user=%s action=%s", entry["thread_id"], entry["user_id"], entry["action"])
    else:
        logger.info("No threads to migrate.")

    if agent_report:
        logger.info("Agent migration report:")
        for entry in agent_report:
            logger.info("  agent=%s user=%s action=%s", entry["agent"], entry["user_id"], entry["action"])
    else:
        logger.info("No agents to migrate.")

    unowned = [e for e in report if e["action"] == "missing_owner"]
    if unowned:
        logger.warning("%d thread(s) had no owner and were not migrated:", len(unowned))
        for e in unowned:
            logger.warning("  %s", e["thread_id"])

    if args.mapping_log:
        mapping_path = paths.base_dir / args.mapping_log
        if not args.dry_run:
            mapping_path.parent.mkdir(parents=True, exist_ok=True)
            with mapping_path.open("a", encoding="utf-8") as f:
                for entry in report:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        logger.info("Mapping log path: %s", mapping_path)


if __name__ == "__main__":
    main()
