"""Simple in-memory sliding-window rate limiter for public agent proxy."""

from __future__ import annotations

import threading
import time
from collections import deque


class SlidingWindowLimiter:
    def __init__(self, max_events: int = 120, window_seconds: float = 60.0) -> None:
        self._max = max_events
        self._window = window_seconds
        self._data: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            dq = self._data.setdefault(key, deque())
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= self._max:
                return False
            dq.append(now)
            return True
