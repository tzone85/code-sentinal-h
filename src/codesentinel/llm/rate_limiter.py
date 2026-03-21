"""Async rate limiter using semaphore and sliding-window RPM control."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from types import TracebackType


class RateLimiter:
    """Limits concurrent requests and enforces a requests-per-minute ceiling.

    Uses an asyncio.Semaphore for concurrency and a sliding 60-second
    window of timestamps for RPM enforcement.  Designed as an async
    context manager so callers can simply ``async with limiter:``.
    """

    def __init__(
        self,
        *,
        max_concurrent: int = 3,
        requests_per_minute: int = 50,
    ) -> None:
        if max_concurrent < 1:
            msg = "max_concurrent must be at least 1"
            raise ValueError(msg)
        if requests_per_minute < 1:
            msg = "requests_per_minute must be at least 1"
            raise ValueError(msg)

        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._rpm = requests_per_minute
        self._window: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait for a concurrency slot and an RPM budget token."""
        await self._semaphore.acquire()
        try:
            await self._wait_for_rpm_budget()
        except BaseException:
            self._semaphore.release()
            raise

    async def _wait_for_rpm_budget(self) -> None:
        """Sleep until the sliding window has room for one more request."""
        while True:
            async with self._lock:
                now = time.monotonic()
                window_start = now - 60.0

                # Evict timestamps older than the window.
                while self._window and self._window[0] <= window_start:
                    self._window.popleft()

                if len(self._window) < self._rpm:
                    self._window.append(now)
                    return

                # Must wait until the oldest entry exits the window.
                sleep_for = self._window[0] - window_start

            await asyncio.sleep(sleep_for)

    def release(self) -> None:
        """Release the concurrency slot."""
        self._semaphore.release()

    async def __aenter__(self) -> RateLimiter:
        await self.acquire()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.release()
