"""Stream bridge channel id for thread-level async_task SSE (not tied to a single run)."""


def sse_channel_for_thread(thread_id: str) -> str:
    return f"async_task:{thread_id}"
