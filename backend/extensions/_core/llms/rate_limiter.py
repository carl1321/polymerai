# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
LLM 调用限流器（兼容 agentic_workflow）。

默认限制 1 秒内最多 5 次调用，避免某些 provider 的 rate limit。
"""

import asyncio
import logging
import time
from collections import deque

logger = logging.getLogger(__name__)


class LLMRateLimiter:
    def __init__(self, max_calls: int = 5, time_window: float = 1.0):
        self.max_calls = max_calls
        self.time_window = time_window
        self._call_times: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            current_time = time.time()
            while self._call_times and current_time - self._call_times[0] > self.time_window:
                self._call_times.popleft()

            if len(self._call_times) >= self.max_calls:
                oldest_call_time = self._call_times[0]
                wait_time = self.time_window - (current_time - oldest_call_time) + 0.01
                if wait_time > 0:
                    logger.debug(
                        "Rate limit reached (%d/%d calls in %.2fs), waiting %.2fs",
                        len(self._call_times),
                        self.max_calls,
                        self.time_window,
                        wait_time,
                    )
                    await asyncio.sleep(wait_time)

                    current_time = time.time()
                    while self._call_times and current_time - self._call_times[0] > self.time_window:
                        self._call_times.popleft()

            self._call_times.append(time.time())


_global_rate_limiter: LLMRateLimiter | None = None


def get_llm_rate_limiter() -> LLMRateLimiter:
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = LLMRateLimiter(max_calls=5, time_window=1.0)
    return _global_rate_limiter


async def acquire_llm_call_permission() -> None:
    limiter = get_llm_rate_limiter()
    await limiter.acquire()
