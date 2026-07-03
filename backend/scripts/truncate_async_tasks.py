#!/usr/bin/env python3
"""Truncate the async_tasks table (PostgreSQL). Uses same DB URL as init_app_database.py.

Run from backend: uv run python scripts/truncate_async_tasks.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    from extensions._core.app_db import get_app_db_connection
    from scripts.init_app_database import get_connection_url

    url = get_connection_url()
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgres://", 1)
    conn = get_app_db_connection(url)
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE async_tasks RESTART IDENTITY CASCADE")
        conn.commit()
        logger.info("async_tasks truncated.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
