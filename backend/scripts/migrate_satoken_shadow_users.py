"""Remove or report Sa-Token shadow users (username satoken_*) after identity fix.

These accounts were created when local username was derived from login id instead of
ContiNew username. Re-login with Sa-Token should bind to the real admin user.

Usage:
    PYTHONPATH=. python scripts/migrate_satoken_shadow_users.py [--dry-run] [--delete]

Default: print shadow users only. Pass --delete to remove inactive shadow rows (no resource merge).
"""

from __future__ import annotations

import argparse
import logging
import sys

from extensions.auth.db import UserDB

logger = logging.getLogger(__name__)


def _list_shadow_users() -> list[dict]:
    from deerflow.persistence.engine import get_app_db_connection

    conn = get_app_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, username, email, is_superuser, oauth_provider, oauth_id
                FROM users
                WHERE username LIKE 'satoken_%'
                ORDER BY username
                """
            )
            return list(cursor.fetchall())
    finally:
        conn.close()


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="List or delete satoken_* shadow users")
    parser.add_argument("--dry-run", action="store_true", help="With --delete, only log actions")
    parser.add_argument("--delete", action="store_true", help="Delete shadow users (use after verifying admin login)")
    args = parser.parse_args()

    rows = _list_shadow_users()
    if not rows:
        logger.info("No satoken_* shadow users found.")
        return 0

    for row in rows:
        logger.info(
            "shadow user: id=%s username=%s email=%s superuser=%s oauth=%s:%s",
            row.get("id"),
            row.get("username"),
            row.get("email"),
            row.get("is_superuser"),
            row.get("oauth_provider"),
            row.get("oauth_id"),
        )

    if not args.delete:
        logger.info("Found %s shadow user(s). Re-login as admin, then run with --delete if safe.", len(rows))
        return 0

    for row in rows:
        uid = row["id"]
        if args.dry_run:
            logger.info("[dry-run] would delete user %s (%s)", uid, row.get("username"))
            continue
        from uuid import UUID

        user_uuid = uid if isinstance(uid, UUID) else UUID(str(uid))
        if UserDB.delete_user(user_uuid):
            logger.info("Deleted shadow user %s (%s)", uid, row.get("username"))
        else:
            logger.error("Failed to delete user %s (%s)", uid, row.get("username"))
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
