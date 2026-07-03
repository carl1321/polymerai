"""Workflow worker entrypoint (DB queue consumer)."""

import asyncio
import logging
import os

from extensions._core.workflow.runtime.executor import WorkflowExecutor
from extensions._core.workflow.runtime.worker import get_workflow_worker

logger = logging.getLogger(__name__)


def _get_float(name: str, default: float) -> float:
    v = os.environ.get(name)
    if v is None or not str(v).strip():
        return default
    try:
        return float(v)
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if v is None or not str(v).strip():
        return default
    try:
        return int(v)
    except ValueError:
        return default


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    poll_interval = _get_float("DEER_FLOW_WORKFLOW_POLL_INTERVAL", 1.0)
    heartbeat_interval = _get_float("DEER_FLOW_WORKFLOW_HEARTBEAT_INTERVAL", 30.0)
    stale_timeout_minutes = _get_int("DEER_FLOW_WORKFLOW_STALE_TIMEOUT_MINUTES", 5)

    worker = get_workflow_worker()
    # override defaults
    worker.poll_interval = poll_interval
    worker.heartbeat_interval = heartbeat_interval
    worker.stale_timeout_minutes = stale_timeout_minutes
    worker.set_executor(WorkflowExecutor())

    logger.info(
        "Starting workflow worker (poll=%.2fs heartbeat=%.2fs stale=%dmin)",
        poll_interval,
        heartbeat_interval,
        stale_timeout_minutes,
    )
    await worker.start()
    # Block forever
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())

