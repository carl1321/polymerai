"""Gate check for threads_meta indexes and 10k search performance.

Usage:
    uv run python backend/scripts/gate_threads_search_perf.py --prepare
    uv run python backend/scripts/gate_threads_search_perf.py
"""

from __future__ import annotations

import argparse
import asyncio
import random
import string
import sys
import time
from contextlib import AsyncExitStack
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS_SRC = ROOT / "backend" / "packages" / "harness"
if str(HARNESS_SRC) not in sys.path:
    sys.path.insert(0, str(HARNESS_SRC))

from sqlalchemy import text

from deerflow.config.app_config import get_app_config
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.thread_meta import ThreadMetaRepository


def _rand_suffix(n: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


async def _check_indexes(repo: ThreadMetaRepository) -> list[str]:
    missing: list[str] = []
    async with repo._sf() as session:  # noqa: SLF001
        dialect = session.bind.dialect.name if session.bind is not None else ""
        if dialect == "sqlite":
            rows = await session.execute(text("PRAGMA index_list('threads_meta')"))
            names = {row[1] for row in rows.fetchall()}
        else:
            rows = await session.execute(
                text(
                    "SELECT indexname FROM pg_indexes WHERE tablename='threads_meta'"
                )
            )
            names = {row[0] for row in rows.fetchall()}

    required = {
        "ix_threads_meta_user_updated",
        "ix_threads_meta_user_status_updated",
    }
    for name in required:
        if name not in names:
            missing.append(name)
    return missing


async def _prepare_dataset(repo: ThreadMetaRepository, *, user_id: str, count: int) -> None:
    existing = await repo.search(user_id=user_id, limit=1, offset=0)
    if existing:
        return

    for idx in range(count):
        tid = f"perf-{idx:05d}-{_rand_suffix(4)}"
        status = "busy" if idx % 3 == 0 else "idle"
        await repo.create(
            tid,
            user_id=user_id,
            display_name=f"Perf Thread {idx}",
            metadata={"topic": "perf", "bucket": idx % 10},
        )
        if status != "idle":
            await repo.update_status(tid, status, user_id=user_id)


async def _bench(repo: ThreadMetaRepository, *, user_id: str, iterations: int, limit: int) -> float:
    latencies_ms: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        await repo.search(
            user_id=user_id,
            status="busy",
            metadata={"topic": "perf"},
            limit=limit,
            offset=0,
        )
        latencies_ms.append((time.perf_counter() - t0) * 1000)
    latencies_ms.sort()
    idx = min(len(latencies_ms) - 1, int(len(latencies_ms) * 0.95))
    return latencies_ms[idx]


async def _run(*, prepare: bool, rows: int, p95_target: float) -> int:
    cfg = get_app_config()
    await init_engine_from_config(cfg.database)
    sf = get_session_factory()
    if sf is None:
        raise RuntimeError("database backend is memory; cannot run threads_meta gate")

    async with AsyncExitStack():
        repo = ThreadMetaRepository(sf)
        missing = await _check_indexes(repo)
        if missing:
            print("index_check=FAILED")
            print(f"missing_indexes={','.join(missing)}")
            return 1
        print("index_check=OK")

        user_id = "perf-gate-user"
        if prepare:
            await _prepare_dataset(repo, user_id=user_id, count=rows)
            print(f"dataset_prepare=OK rows={rows}")

        p95_ms = await _bench(repo, user_id=user_id, iterations=30, limit=50)
        print(f"threads_search_p95_ms={p95_ms:.2f}")
        print(f"p95_target_ms={p95_target:.2f}")
        if p95_ms > p95_target:
            print("perf_gate=FAILED")
            return 2
        print("perf_gate=OK")
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="threads_meta index/perf gate")
    parser.add_argument("--prepare", action="store_true", help="Seed 10k perf dataset if missing")
    parser.add_argument("--rows", type=int, default=10000, help="Rows to seed when --prepare is enabled")
    parser.add_argument("--p95-target-ms", type=float, default=200.0, help="Fail if measured p95 exceeds this")
    args = parser.parse_args()
    try:
        code = asyncio.run(_run(prepare=args.prepare, rows=args.rows, p95_target=args.p95_target_ms))
    finally:
        asyncio.run(close_engine())
    raise SystemExit(code)


if __name__ == "__main__":
    main()
