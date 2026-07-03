#!/usr/bin/env python3
"""Align chat persistence ``user_id`` with ``threads_meta`` (single source of truth).

Correspondence (see ``backend/docs/THREAD_SESSION_AND_USER_ID.md``):

- **thread_id** — same UUID links ``threads_meta``, ``checkpoints``, ``runs``,
  ``run_events``, and ``store`` (prefix ``threads``, key = thread_id).
- **user_id** — must match ``users.id``; ``GET .../runs`` uses
  ``WHERE runs.user_id = current_user``, so **NULL user_id on runs never
  matches** and the list is empty (HTTP 200 + ``[]``).

Execution order (single transaction):

1. **Fill** ``threads_meta.user_id`` when it is NULL, using the latest
   ``checkpoints.metadata->>user_id`` for that thread (migration gaps).
2. **Propagate** ``threads_meta.user_id`` into ``checkpoints.metadata``,
   ``store.value.metadata``, ``runs``, ``run_events``.

Does **not** modify ``workflow_ckpt`` or other schemas.

Usage::

    uv run python backend/scripts/normalize_chat_owner_from_threads_meta.py --dry-run
    uv run python backend/scripts/normalize_chat_owner_from_threads_meta.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError as e:  # pragma: no cover
    print("psycopg is required: pip/uv add psycopg[binary]", file=sys.stderr)
    raise SystemExit(1) from e


def _load_pg_url_from_config() -> str | None:
    root = Path(__file__).resolve().parents[2]
    cfg = root / "config.yaml"
    if not cfg.is_file():
        return None
    try:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    db = (data or {}).get("database") or {}
    return (db.get("postgres_url") or "").strip() or None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument(
        "--pg-url",
        default=os.environ.get("DEERFLOW_PG_URL", "") or _load_pg_url_from_config() or "",
        help="PostgreSQL connection string (or set DEERFLOW_PG_URL / config.yaml database.postgres_url).",
    )
    p.add_argument(
        "--store-prefix",
        default="threads",
        help="LangGraph store namespace prefix for thread documents (default: threads).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print how many rows would change; no updates.",
    )
    args = p.parse_args()
    if not args.pg_url.strip():
        print("Missing --pg-url (or DEERFLOW_PG_URL / config.yaml database.postgres_url).", file=sys.stderr)
        return 2

    conn_kw: dict = {"row_factory": dict_row}
    if args.pg_url.startswith("postgres://"):
        conn_kw["conninfo"] = args.pg_url.replace("postgres://", "postgresql://", 1)
    else:
        conn_kw["conninfo"] = args.pg_url

    plan_sql = """
    SELECT
      (SELECT COUNT(*)::bigint
         FROM public.threads_meta tm
         WHERE tm.user_id IS NULL
           AND EXISTS (
             SELECT 1 FROM public.checkpoints c
             WHERE c.thread_id = tm.thread_id
               AND NULLIF(btrim(c.metadata->>'user_id'), '') IS NOT NULL
           )) AS threads_meta_fill,
      (SELECT COUNT(*)::bigint FROM public.checkpoints c
         INNER JOIN public.threads_meta tm ON c.thread_id = tm.thread_id
         WHERE tm.user_id IS NOT NULL
           AND (COALESCE(c.metadata, '{}'::jsonb)->>'user_id' IS DISTINCT FROM tm.user_id)) AS checkpoints,
      (SELECT COUNT(*)::bigint FROM public.store s
         INNER JOIN public.threads_meta tm ON s.key = tm.thread_id AND s.prefix = %s
         WHERE tm.user_id IS NOT NULL
           AND (COALESCE(s.value->'metadata'->>'user_id', '') IS DISTINCT FROM tm.user_id)) AS store_rows,
      (SELECT COUNT(*)::bigint FROM public.runs r
         INNER JOIN public.threads_meta tm ON r.thread_id = tm.thread_id
         WHERE tm.user_id IS NOT NULL
           AND (r.user_id IS DISTINCT FROM tm.user_id)) AS runs_rows,
      (SELECT COUNT(*)::bigint FROM public.run_events e
         INNER JOIN public.threads_meta tm ON e.thread_id = tm.thread_id
         WHERE tm.user_id IS NOT NULL
           AND (e.user_id IS DISTINCT FROM tm.user_id)) AS run_events_rows;
    """

    updates: list[tuple[str, str] | tuple[str, str, tuple]] = [
        (
            "threads_meta.user_id (from checkpoints.metadata, only where NULL)",
            """
            UPDATE public.threads_meta AS tm
            SET user_id = src.owner_uid
            FROM (
              SELECT DISTINCT ON (c.thread_id)
                c.thread_id,
                NULLIF(btrim(c.metadata->>'user_id'), '') AS owner_uid
              FROM public.checkpoints c
              WHERE c.metadata->>'user_id' IS NOT NULL
                AND NULLIF(btrim(c.metadata->>'user_id'), '') IS NOT NULL
              ORDER BY c.thread_id, c.checkpoint_id DESC
            ) AS src
            WHERE tm.thread_id = src.thread_id
              AND tm.user_id IS NULL
              AND src.owner_uid IS NOT NULL
            """,
        ),
        (
            "checkpoints.metadata.user_id",
            """
            UPDATE public.checkpoints AS c
            SET metadata = COALESCE(c.metadata, '{}'::jsonb)
              || jsonb_build_object('user_id', tm.user_id)
            FROM public.threads_meta AS tm
            WHERE c.thread_id = tm.thread_id
              AND tm.user_id IS NOT NULL
              AND (COALESCE(c.metadata, '{}'::jsonb)->>'user_id' IS DISTINCT FROM tm.user_id)
            """,
        ),
        (
            "store.value.metadata.user_id",
            """
            UPDATE public.store AS s
            SET value = jsonb_set(
                  COALESCE(s.value, '{}'::jsonb),
                  '{metadata}',
                  COALESCE(s.value->'metadata', '{}'::jsonb)
                    || jsonb_build_object('user_id', tm.user_id),
                  true
                ),
                updated_at = CURRENT_TIMESTAMP
            FROM public.threads_meta AS tm
            WHERE s.prefix = %s
              AND s.key = tm.thread_id
              AND tm.user_id IS NOT NULL
              AND (COALESCE(s.value->'metadata'->>'user_id', '')
                     IS DISTINCT FROM tm.user_id)
            """,
            (args.store_prefix,),
        ),
        (
            "runs.user_id",
            """
            UPDATE public.runs AS r
            SET user_id = tm.user_id
            FROM public.threads_meta AS tm
            WHERE r.thread_id = tm.thread_id
              AND tm.user_id IS NOT NULL
              AND (r.user_id IS DISTINCT FROM tm.user_id)
            """,
        ),
        (
            "run_events.user_id",
            """
            UPDATE public.run_events AS e
            SET user_id = tm.user_id
            FROM public.threads_meta AS tm
            WHERE e.thread_id = tm.thread_id
              AND tm.user_id IS NOT NULL
              AND (e.user_id IS DISTINCT FROM tm.user_id)
            """,
        ),
    ]

    with psycopg.connect(**conn_kw) as conn:
        with conn.cursor() as cur:
            cur.execute(plan_sql, (args.store_prefix,))
            row = cur.fetchone() or {}
            tfill = int(row.get("threads_meta_fill") or 0)
            ck = int(row.get("checkpoints") or 0)
            st = int(row.get("store_rows") or 0)
            rn = int(row.get("runs_rows") or 0)
            ev = int(row.get("run_events_rows") or 0)
        print(
            "plan:",
            f"threads_meta_fill={tfill}, checkpoints={ck}, store={st}, runs={rn}, run_events={ev}",
            "(rows needing updates)",
        )
        if args.dry_run:
            return 0

        total = 0
        with conn.transaction():
            with conn.cursor() as cur:
                for spec in updates:
                    label = spec[0]
                    sql = spec[1]
                    extra = spec[2] if len(spec) > 2 else ()
                    cur.execute(sql, extra)
                    n = cur.rowcount
                    total += n
                    print(f"updated {label}: {n} rows")
        print(f"done. total row updates (sum): {total}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
