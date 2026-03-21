"""Tests for the async RateLimiter."""

from __future__ import annotations

import asyncio

import pytest

from codesentinel.llm.rate_limiter import RateLimiter


class TestRateLimiterInit:
    """Test RateLimiter construction and validation."""

    def test_default_values(self) -> None:
        limiter = RateLimiter()
        assert limiter._rpm == 50
        assert limiter._semaphore._value == 3

    def test_custom_values(self) -> None:
        limiter = RateLimiter(max_concurrent=5, requests_per_minute=100)
        assert limiter._rpm == 100
        assert limiter._semaphore._value == 5

    def test_rejects_zero_concurrent(self) -> None:
        with pytest.raises(ValueError, match="max_concurrent"):
            RateLimiter(max_concurrent=0)

    def test_rejects_negative_concurrent(self) -> None:
        with pytest.raises(ValueError, match="max_concurrent"):
            RateLimiter(max_concurrent=-1)

    def test_rejects_zero_rpm(self) -> None:
        with pytest.raises(ValueError, match="requests_per_minute"):
            RateLimiter(requests_per_minute=0)

    def test_rejects_negative_rpm(self) -> None:
        with pytest.raises(ValueError, match="requests_per_minute"):
            RateLimiter(requests_per_minute=-1)


class TestRateLimiterSemaphore:
    """Test concurrency limiting via semaphore."""

    async def test_limits_concurrent_requests(self) -> None:
        limiter = RateLimiter(max_concurrent=2, requests_per_minute=100)
        active = 0
        max_active = 0

        async def task() -> None:
            nonlocal active, max_active
            async with limiter:
                active += 1
                max_active = max(max_active, active)
                await asyncio.sleep(0.01)
                active -= 1

        await asyncio.gather(*(task() for _ in range(6)))
        assert max_active <= 2

    async def test_acquire_release_symmetry(self) -> None:
        limiter = RateLimiter(max_concurrent=1, requests_per_minute=100)
        await limiter.acquire()
        limiter.release()
        # Should be acquirable again immediately.
        await limiter.acquire()
        limiter.release()


class TestRateLimiterRPM:
    """Test RPM sliding window enforcement."""

    async def test_allows_requests_within_rpm(self) -> None:
        limiter = RateLimiter(max_concurrent=10, requests_per_minute=10)
        for _ in range(10):
            async with limiter:
                pass  # Should not block.

    async def test_rpm_window_eviction(self) -> None:
        """Timestamps older than 60s are evicted from the window."""
        limiter = RateLimiter(max_concurrent=10, requests_per_minute=5)
        # Fill the window.
        for _ in range(5):
            async with limiter:
                pass
        assert len(limiter._window) == 5


class TestRateLimiterContextManager:
    """Test async context manager protocol."""

    async def test_async_with_acquires_and_releases(self) -> None:
        limiter = RateLimiter(max_concurrent=1, requests_per_minute=100)
        async with limiter:
            # Semaphore should be held.
            assert limiter._semaphore._value == 0
        # Semaphore should be released.
        assert limiter._semaphore._value == 1

    async def test_releases_on_exception(self) -> None:
        limiter = RateLimiter(max_concurrent=1, requests_per_minute=100)
        with pytest.raises(RuntimeError, match="boom"):
            async with limiter:
                raise RuntimeError("boom")
        # Semaphore must still be released.
        assert limiter._semaphore._value == 1

    async def test_returns_self(self) -> None:
        limiter = RateLimiter()
        async with limiter as ctx:
            assert ctx is limiter
