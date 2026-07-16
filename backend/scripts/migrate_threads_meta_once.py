"""One-time migration from legacy SQLite checkpoints/store.

Supports:
1) SQLite -> SQLite threads_meta migration
2) SQLite -> PostgreSQL migration (threads_meta + checkpoints + writes + store)
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import msgpack
import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHECKPOINTS_DB = ROOT / "backend/.deer-flow/checkpoints.db"
DEFAULT_APP_DB = ROOT / "backend/.deer-flow/data/deerflow.db"


def _safe_json_loads(raw: str | bytes | None) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except Exception:
            return {}
    try:
        val = json.loads(raw)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _to_iso(value) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), UTC).isoformat()
        except Exception:
            return None
    return None


def _to_json_text(value) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        default=lambda obj: obj.hex() if isinstance(obj, (bytes, bytearray)) else str(obj),
    )


def _fetch_store_candidates(cp_conn: sqlite3.Connection, limit: int) -> dict[str, dict]:
    rows = cp_conn.execute(
        """
        SELECT key, value
        FROM store
        WHERE prefix='["threads"]'
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    candidates: dict[str, dict] = {}
    for key, value in rows:
        payload = _safe_json_loads(value)
        thread_id = payload.get("thread_id") or key
        if isinstance(thread_id, str) and thread_id:
            payload["thread_id"] = thread_id
            candidates[thread_id] = payload
    return candidates


def _merge_checkpoints(cp_conn: sqlite3.Connection, candidates: dict[str, dict], limit: int) -> None:
    rows = cp_conn.execute(
        """
        SELECT thread_id, checkpoint_ns, checkpoint, metadata
        FROM checkpoints
        WHERE checkpoint_ns=''
        ORDER BY rowid DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    for thread_id, _ns, checkpoint_blob, metadata_blob in rows:
        if not isinstance(thread_id, str) or not thread_id:
            continue
        row = candidates.setdefault(thread_id, {"thread_id": thread_id, "metadata": {}, "values": {}})
        metadata = row.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            row["metadata"] = metadata

        ckpt_meta = _safe_json_loads(metadata_blob)
        owner = ckpt_meta.get("user_id")
        if isinstance(owner, str) and owner.strip():
            metadata.setdefault("user_id", owner.strip())

        created_at = _to_iso(ckpt_meta.get("created_at"))
        updated_at = _to_iso(ckpt_meta.get("updated_at"))
        if created_at:
            metadata.setdefault("legacy_created_at", created_at)
        if updated_at:
            metadata.setdefault("legacy_updated_at", updated_at)

        try:
            checkpoint = msgpack.unpackb(checkpoint_blob, raw=False)
        except Exception:
            continue
        if not isinstance(checkpoint, dict):
            continue
        channel_values = checkpoint.get("channel_values") or {}
        if isinstance(channel_values, dict):
            title = channel_values.get("title")
            if isinstance(title, str) and title.strip():
                row.setdefault("values", {})
                if isinstance(row["values"], dict):
                    row["values"].setdefault("title", title.strip())
                metadata.setdefault("title", title.strip())
        ts = _to_iso(checkpoint.get("ts"))
        if ts:
            metadata.setdefault("legacy_updated_at", ts)


def _ensure_pg_tables(pg_conn: psycopg.Connection) -> None:
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
              feedback_id VARCHAR(64) PRIMARY KEY,
              run_id VARCHAR(64) NOT NULL,
              thread_id VARCHAR(64) NOT NULL,
              user_id VARCHAR(64),
              message_id VARCHAR(64),
              rating INTEGER NOT NULL,
              comment TEXT,
              created_at TIMESTAMPTZ NOT NULL
            );
            """
        )
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_feedback_thread_run_user ON feedback (thread_id, run_id, user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_feedback_thread_id ON feedback (thread_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_feedback_run_id ON feedback (run_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_feedback_user_id ON feedback (user_id)")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS run_events (
              id BIGSERIAL PRIMARY KEY,
              thread_id VARCHAR(64) NOT NULL,
              run_id VARCHAR(64) NOT NULL,
              user_id VARCHAR(64),
              event_type VARCHAR(32) NOT NULL,
              category VARCHAR(16) NOT NULL,
              content TEXT NOT NULL,
              event_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
              seq INTEGER NOT NULL,
              created_at TIMESTAMPTZ NOT NULL,
              CONSTRAINT uq_events_thread_seq UNIQUE (thread_id, seq)
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS ix_run_events_user_id ON run_events (user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_events_run ON run_events (thread_id, run_id, seq)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_events_thread_cat_seq ON run_events (thread_id, category, seq)")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
              run_id VARCHAR(64) PRIMARY KEY,
              thread_id VARCHAR(64) NOT NULL,
              assistant_id VARCHAR(128),
              user_id VARCHAR(64),
              status VARCHAR(20) NOT NULL,
              model_name VARCHAR(128),
              multitask_strategy VARCHAR(20) NOT NULL,
              metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
              kwargs_json JSONB NOT NULL DEFAULT '{}'::jsonb,
              error TEXT,
              message_count INTEGER NOT NULL DEFAULT 0,
              first_human_message TEXT,
              last_ai_message TEXT,
              total_input_tokens INTEGER NOT NULL DEFAULT 0,
              total_output_tokens INTEGER NOT NULL DEFAULT 0,
              total_tokens INTEGER NOT NULL DEFAULT 0,
              llm_call_count INTEGER NOT NULL DEFAULT 0,
              lead_agent_tokens INTEGER NOT NULL DEFAULT 0,
              subagent_tokens INTEGER NOT NULL DEFAULT 0,
              middleware_tokens INTEGER NOT NULL DEFAULT 0,
              follow_up_to_run_id VARCHAR(64),
              started_at TIMESTAMPTZ,
              finished_at TIMESTAMPTZ,
              duration_ms INTEGER,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS ix_runs_thread_status ON runs (thread_id, status)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_runs_thread_id ON runs (thread_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_runs_user_id ON runs (user_id)")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS threads_meta (
              thread_id VARCHAR(64) PRIMARY KEY,
              assistant_id VARCHAR(128),
              user_id VARCHAR(64),
              display_name VARCHAR(256),
              status VARCHAR(20) NOT NULL DEFAULT 'idle',
              metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS ix_threads_meta_user_id ON threads_meta (user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_threads_meta_assistant_id ON threads_meta (assistant_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_threads_meta_user_updated ON threads_meta (user_id, updated_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_threads_meta_user_status_updated ON threads_meta (user_id, status, updated_at DESC)")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
              id VARCHAR(36) PRIMARY KEY,
              email VARCHAR(320) NOT NULL,
              password_hash VARCHAR(128),
              system_role VARCHAR(16) NOT NULL,
              created_at TIMESTAMPTZ NOT NULL,
              oauth_provider VARCHAR(32),
              oauth_id VARCHAR(128),
              needs_setup BOOLEAN NOT NULL DEFAULT TRUE,
              token_version INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(320)")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(128)")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS system_role VARCHAR(16)")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_provider VARCHAR(32)")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_id VARCHAR(128)")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS needs_setup BOOLEAN")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER")
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)")
        cur.execute(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='users' AND column_name='oauth_provider'
              ) AND EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='users' AND column_name='oauth_id'
              ) THEN
                CREATE UNIQUE INDEX IF NOT EXISTS idx_users_oauth_identity
                ON users (oauth_provider, oauth_id)
                WHERE oauth_provider IS NOT NULL AND oauth_id IS NOT NULL;
              END IF;
            END
            $$;
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS checkpoints (
              thread_id TEXT NOT NULL,
              checkpoint_ns TEXT NOT NULL DEFAULT '',
              checkpoint_id TEXT NOT NULL,
              parent_checkpoint_id TEXT,
              type TEXT,
              checkpoint BYTEA,
              metadata BYTEA,
              PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS writes (
              thread_id TEXT NOT NULL,
              checkpoint_ns TEXT NOT NULL DEFAULT '',
              checkpoint_id TEXT NOT NULL,
              task_id TEXT NOT NULL,
              idx INTEGER NOT NULL,
              channel TEXT NOT NULL,
              type TEXT,
              value BYTEA,
              PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS store (
              prefix TEXT NOT NULL,
              key TEXT NOT NULL,
              value TEXT NOT NULL,
              created_at TIMESTAMPTZ DEFAULT NOW(),
              updated_at TIMESTAMPTZ DEFAULT NOW(),
              expires_at TIMESTAMPTZ,
              ttl_minutes DOUBLE PRECISION,
              PRIMARY KEY (prefix, key)
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS store_prefix_idx ON store (prefix)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_store_expires_at ON store (expires_at)")
        cur.execute("CREATE TABLE IF NOT EXISTS store_migrations (v INTEGER PRIMARY KEY)")


def _migrate_checkpoint_tables_to_pg(cp_conn: sqlite3.Connection, pg_conn: psycopg.Connection, dry_run: bool) -> dict[str, int]:
    ck_rows = cp_conn.execute("SELECT thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata FROM checkpoints").fetchall()
    wr_rows = cp_conn.execute("SELECT thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, type, value FROM writes").fetchall()
    st_rows = cp_conn.execute("SELECT prefix, key, value, created_at, updated_at, expires_at, ttl_minutes FROM store").fetchall()

    if dry_run:
        return {"checkpoints": len(ck_rows), "writes": len(wr_rows), "store": len(st_rows)}

    checkpoint_col_types: dict[str, str] = {}
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='checkpoints'
            """
        )
        checkpoint_col_types = {row["column_name"]: row["data_type"] for row in cur.fetchall()}
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='store'
            """
        )
        store_col_types = {row["column_name"]: row["data_type"] for row in cur.fetchall()}

    checkpoint_is_jsonb = checkpoint_col_types.get("checkpoint") == "jsonb"
    metadata_is_jsonb = checkpoint_col_types.get("metadata") == "jsonb"
    store_value_is_jsonb = store_col_types.get("value") == "jsonb"

    with pg_conn.cursor() as cur:
        for row in ck_rows:
            thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, row_type, checkpoint, metadata = row
            checkpoint_value = checkpoint
            metadata_value = metadata
            if checkpoint_is_jsonb:
                if isinstance(checkpoint, (bytes, bytearray)):
                    try:
                        checkpoint_value = msgpack.unpackb(checkpoint, raw=False)
                    except Exception:
                        checkpoint_value = _safe_json_loads(checkpoint)
                elif isinstance(checkpoint, str):
                    checkpoint_value = _safe_json_loads(checkpoint)
                else:
                    checkpoint_value = checkpoint
                if not isinstance(checkpoint_value, str):
                    checkpoint_value = _to_json_text(checkpoint_value)
            if metadata_is_jsonb:
                if isinstance(metadata, (bytes, bytearray)):
                    try:
                        metadata_value = msgpack.unpackb(metadata, raw=False)
                    except Exception:
                        metadata_value = _safe_json_loads(metadata)
                elif isinstance(metadata, str):
                    metadata_value = _safe_json_loads(metadata)
                else:
                    metadata_value = metadata
                if not isinstance(metadata_value, str):
                    metadata_value = _to_json_text(metadata_value)
            cur.execute(
                """
                INSERT INTO checkpoints(thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (thread_id, checkpoint_ns, checkpoint_id)
                DO UPDATE SET parent_checkpoint_id=EXCLUDED.parent_checkpoint_id,
                              type=EXCLUDED.type,
                              checkpoint=EXCLUDED.checkpoint,
                              metadata=EXCLUDED.metadata
                """,
                (
                    thread_id,
                    checkpoint_ns,
                    checkpoint_id,
                    parent_checkpoint_id,
                    row_type,
                    checkpoint_value,
                    metadata_value,
                ),
            )
        for row in wr_rows:
            cur.execute(
                """
                INSERT INTO writes(thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, type, value)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
                DO UPDATE SET channel=EXCLUDED.channel,
                              type=EXCLUDED.type,
                              value=EXCLUDED.value
                """,
                row,
            )
        for row in st_rows:
            prefix, key, value, created_at, updated_at, expires_at, ttl_minutes = row
            store_value = value
            if store_value_is_jsonb:
                if isinstance(store_value, (bytes, bytearray)):
                    try:
                        store_value = store_value.decode("utf-8")
                    except Exception:
                        store_value = "{}"
                if isinstance(store_value, str):
                    store_value = _to_json_text(_safe_json_loads(store_value))
                else:
                    store_value = _to_json_text(store_value)
            cur.execute(
                (
                    """
                    INSERT INTO store(prefix, key, value, created_at, updated_at, expires_at, ttl_minutes)
                    VALUES (%s,%s,%s::jsonb,%s,%s,%s,%s)
                    ON CONFLICT (prefix, key)
                    DO UPDATE SET value=EXCLUDED.value,
                                  created_at=EXCLUDED.created_at,
                                  updated_at=EXCLUDED.updated_at,
                                  expires_at=EXCLUDED.expires_at,
                                  ttl_minutes=EXCLUDED.ttl_minutes
                    """
                    if store_value_is_jsonb
                    else """
                    INSERT INTO store(prefix, key, value, created_at, updated_at, expires_at, ttl_minutes)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (prefix, key)
                    DO UPDATE SET value=EXCLUDED.value,
                                  created_at=EXCLUDED.created_at,
                                  updated_at=EXCLUDED.updated_at,
                                  expires_at=EXCLUDED.expires_at,
                                  ttl_minutes=EXCLUDED.ttl_minutes
                    """
                ),
                (prefix, key, store_value, created_at, updated_at, expires_at, ttl_minutes),
            )
    return {"checkpoints": len(ck_rows), "writes": len(wr_rows), "store": len(st_rows)}


def migrate_once(
    *,
    checkpoints_db: Path,
    app_db: Path | None,
    target_pg_url: str | None,
    limit: int,
    dry_run: bool,
) -> dict[str, int]:
    cp_conn = sqlite3.connect(str(checkpoints_db))
    cp_conn.row_factory = sqlite3.Row
    app_conn = None
    pg_conn = None
    if target_pg_url:
        pg_conn = psycopg.connect(target_pg_url, row_factory=dict_row)
    elif app_db is not None:
        app_conn = sqlite3.connect(str(app_db))
        app_conn.row_factory = sqlite3.Row
    else:
        raise ValueError("Either app_db or target_pg_url is required")

    try:
        checkpoint_stats = {"checkpoints": 0, "writes": 0, "store": 0}
        if pg_conn is not None:
            _ensure_pg_tables(pg_conn)
            if dry_run:
                pg_conn.commit()
            checkpoint_stats = _migrate_checkpoint_tables_to_pg(cp_conn, pg_conn, dry_run=dry_run)

        candidates = _fetch_store_candidates(cp_conn, limit=limit)
        _merge_checkpoints(cp_conn, candidates, limit=limit)

        migrated = 0
        updated = 0
        skipped_no_owner = 0

        for thread_id, row in candidates.items():
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            owner = None
            if isinstance(row.get("user_id"), str) and row["user_id"].strip():
                owner = row["user_id"].strip()
            elif isinstance(metadata.get("user_id"), str) and metadata["user_id"].strip():
                owner = metadata["user_id"].strip()
            if not owner:
                skipped_no_owner += 1
                continue

            title = None
            values = row.get("values")
            if isinstance(values, dict) and isinstance(values.get("title"), str) and values["title"].strip():
                title = values["title"].strip()
            elif isinstance(metadata.get("title"), str) and metadata["title"].strip():
                title = metadata["title"].strip()

            status = row.get("status") if isinstance(row.get("status"), str) else "idle"
            assistant_id = row.get("assistant_id") if isinstance(row.get("assistant_id"), str) else None
            now = datetime.now(UTC).isoformat()
            legacy_created_at = _to_iso(metadata.get("legacy_created_at")) or _to_iso(row.get("created_at"))
            legacy_updated_at = _to_iso(metadata.get("legacy_updated_at")) or _to_iso(row.get("updated_at"))
            created_at_to_use = legacy_created_at or legacy_updated_at or now
            updated_at_to_use = legacy_updated_at or created_at_to_use

            if pg_conn is not None:
                with pg_conn.cursor() as cur:
                    cur.execute(
                        "SELECT thread_id, user_id, created_at, updated_at FROM threads_meta WHERE thread_id=%s",
                        (thread_id,),
                    )
                    existing = cur.fetchone()
            else:
                existing = app_conn.execute(
                    "SELECT thread_id, user_id, created_at, updated_at FROM threads_meta WHERE thread_id=?",
                    (thread_id,),
                ).fetchone()

            if existing is None:
                migrated += 1
                if not dry_run:
                    if pg_conn is not None:
                        with pg_conn.cursor() as cur:
                            cur.execute(
                                """
                                INSERT INTO threads_meta
                                (thread_id, assistant_id, user_id, display_name, status, metadata_json, created_at, updated_at)
                                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                                """,
                                (
                                    thread_id,
                                    assistant_id,
                                    owner,
                                    title,
                                    status,
                                    json.dumps(metadata, ensure_ascii=False),
                                    created_at_to_use,
                                    updated_at_to_use,
                                ),
                            )
                    else:
                        app_conn.execute(
                            """
                            INSERT INTO threads_meta
                            (thread_id, assistant_id, user_id, display_name, status, metadata_json, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                thread_id,
                                assistant_id,
                                owner,
                                title,
                                status,
                                json.dumps(metadata, ensure_ascii=False),
                                created_at_to_use,
                                updated_at_to_use,
                            ),
                        )
                continue

            updated += 1
            if not dry_run:
                existing_updated_at = existing["updated_at"] if "updated_at" in existing.keys() else None
                keep_created_at = existing["created_at"] if "created_at" in existing.keys() else created_at_to_use
                if pg_conn is not None:
                    with pg_conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE threads_meta
                            SET assistant_id=COALESCE(assistant_id, %s),
                                user_id=COALESCE(NULLIF(user_id,''), %s),
                                display_name=COALESCE(NULLIF(display_name,''), %s),
                                status=%s,
                                metadata_json=%s::jsonb,
                                created_at=%s,
                                updated_at=%s
                            WHERE thread_id=%s
                            """,
                            (
                                assistant_id,
                                owner,
                                title,
                                status,
                                json.dumps(metadata, ensure_ascii=False),
                                keep_created_at,
                                (legacy_updated_at or existing_updated_at or now),
                                thread_id,
                            ),
                        )
                else:
                    app_conn.execute(
                        """
                        UPDATE threads_meta
                        SET assistant_id=COALESCE(assistant_id, ?),
                            user_id=COALESCE(NULLIF(user_id,''), ?),
                            display_name=COALESCE(NULLIF(display_name,''), ?),
                            status=?,
                            metadata_json=?,
                            created_at=?,
                            updated_at=?
                        WHERE thread_id=?
                        """,
                        (
                            assistant_id,
                            owner,
                            title,
                            status,
                            json.dumps(metadata, ensure_ascii=False),
                            keep_created_at,
                            (legacy_updated_at or existing_updated_at or now),
                            thread_id,
                        ),
                    )

        if not dry_run and app_conn is not None:
            app_conn.commit()
        if not dry_run and pg_conn is not None:
            pg_conn.commit()

        return {
            "candidates": len(candidates),
            "migrated": migrated,
            "updated": updated,
            "skipped_no_owner": skipped_no_owner,
            "checkpoints_migrated": checkpoint_stats["checkpoints"],
            "writes_migrated": checkpoint_stats["writes"],
            "store_rows_migrated": checkpoint_stats["store"],
        }
    finally:
        cp_conn.close()
        if app_conn is not None:
            app_conn.close()
        if pg_conn is not None:
            pg_conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="One-time migration from sqlite checkpoints/store")
    parser.add_argument("--checkpoints-db", default=str(DEFAULT_CHECKPOINTS_DB))
    parser.add_argument("--app-db", default=str(DEFAULT_APP_DB), help="SQLite target deerflow.db (ignored when --target-pg-url is set)")
    parser.add_argument("--target-pg-url", default="", help="PostgreSQL target URL (migrate checkpoints/store + threads_meta)")
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = migrate_once(
        checkpoints_db=Path(args.checkpoints_db),
        app_db=None if args.target_pg_url else Path(args.app_db),
        target_pg_url=args.target_pg_url or None,
        limit=args.limit,
        dry_run=args.dry_run,
    )
    print("migration done")
    print(f"dry_run={args.dry_run}")
    print(f"checkpoints_db={args.checkpoints_db}")
    if args.target_pg_url:
        print("target=postgres")
    else:
        print(f"app_db={args.app_db}")
    print(f"candidates={result['candidates']}")
    print(f"migrated={result['migrated']}")
    print(f"updated={result['updated']}")
    print(f"skipped_no_owner={result['skipped_no_owner']}")
    print(f"checkpoints_migrated={result['checkpoints_migrated']}")
    print(f"writes_migrated={result['writes_migrated']}")
    print(f"store_rows_migrated={result['store_rows_migrated']}")


if __name__ == "__main__":
    main()
