#!/usr/bin/env python3
"""Quick PG verification: chat tables exist and user_id columns align with users (spot-check).

Usage:
  uv run python backend/scripts/verify_pg_chat_migration.py postgresql://user:pass@localhost:5432/deerflow
"""

from __future__ import annotations

import sys

import psycopg
from psycopg.rows import dict_row


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "postgresql://postgres:postgres@localhost:5432/deerflow"
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgres://", 1)
    checks = [
        ("threads_meta", "SELECT COUNT(*) AS n FROM threads_meta"),
        ("runs", "SELECT COUNT(*) AS n FROM runs"),
        ("run_events", "SELECT COUNT(*) AS n FROM run_events"),
        ("users", "SELECT COUNT(*) AS n FROM users"),
        (
            "runs_orphan_user",
            """SELECT COUNT(*) AS n FROM runs r
               WHERE r.user_id IS NOT NULL AND NOT EXISTS (
                 SELECT 1 FROM users u WHERE u.id::text = r.user_id)""",
        ),
        (
            "threads_orphan_user",
            """SELECT COUNT(*) AS n FROM threads_meta t
               WHERE t.user_id IS NOT NULL AND t.user_id <> ''
               AND NOT EXISTS (SELECT 1 FROM users u WHERE u.id::text = t.user_id)""",
        ),
    ]
    with psycopg.connect(url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            for label, sql in checks:
                cur.execute(sql)
                row = cur.fetchone()
                print(f"{label}|{row['n']}")
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
