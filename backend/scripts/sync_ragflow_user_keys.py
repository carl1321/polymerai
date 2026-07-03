#!/usr/bin/env python3
"""Backfill users.ragflow_key for users with empty keys.

Usage:
  cd backend && uv run python scripts/sync_ragflow_user_keys.py

Cron example (run every day at 02:00):
  0 2 * * * cd /path/to/deer-flow/backend && /usr/bin/env uv run python scripts/sync_ragflow_user_keys.py >> /tmp/sync_ragflow_user_keys.log 2>&1
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from uuid import UUID

# Ensure backend package imports resolve when running as script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extensions._core.app_db import get_app_db_connection
from extensions._core.ragflow_user_key import (
    fetch_ragflow_key_for_username,
    get_user_api_key_fetch_settings,
)
from extensions.auth.db import UserDB

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def list_users_with_empty_ragflow_key(limit: int | None = None) -> list[dict]:
    conn = get_app_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT id, username, ragflow_key
                FROM users
                WHERE COALESCE(BTRIM(ragflow_key), '') = ''
                ORDER BY created_at ASC
            """
            params: tuple[object, ...] = ()
            if limit and limit > 0:
                sql += " LIMIT %s"
                params = (limit,)
            cursor.execute(sql, params)
            return cursor.fetchall()
    finally:
        conn.close()


def sync_missing_ragflow_keys(*, dry_run: bool = False, limit: int | None = None) -> int:
    base_url, headers = get_user_api_key_fetch_settings()
    if not base_url:
        logger.error("ragflow.user_api_key_fetch_url is not configured; abort.")
        return 1

    users = list_users_with_empty_ragflow_key(limit=limit)
    if not users:
        logger.info("No users with empty ragflow_key.")
        return 0

    logger.info("Found %d users with empty ragflow_key.", len(users))

    updated = 0
    failed = 0
    skipped = 0

    for user in users:
        raw_id = user.get("id")
        username = (user.get("username") or "").strip()
        if not raw_id or not username:
            skipped += 1
            continue

        key = fetch_ragflow_key_for_username(username, base_url, headers)
        if not key:
            logger.warning("fetch failed or empty key for username=%s", username)
            failed += 1
            continue

        if dry_run:
            logger.info("[dry-run] would update username=%s", username)
            updated += 1
            continue

        try:
            user_id = raw_id if isinstance(raw_id, UUID) else UUID(str(raw_id))
            row = UserDB.update_user(user_id, ragflow_key=key)
            if row is None:
                logger.warning("update failed for username=%s", username)
                failed += 1
                continue
            updated += 1
            logger.info("updated ragflow_key for username=%s", username)
        except Exception as exc:
            logger.warning("update exception for username=%s: %s", username, exc)
            failed += 1

    logger.info("sync done: updated=%d failed=%d skipped=%d", updated, failed, skipped)
    return 0 if failed == 0 else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync empty users.ragflow_key from remote API by username")
    parser.add_argument("--dry-run", action="store_true", help="only print actions without database updates")
    parser.add_argument("--limit", type=int, default=0, help="max number of users to process (0 means no limit)")
    args = parser.parse_args()

    limit = args.limit if args.limit and args.limit > 0 else None
    return sync_missing_ragflow_keys(dry_run=args.dry_run, limit=limit)


if __name__ == "__main__":
    raise SystemExit(main())
