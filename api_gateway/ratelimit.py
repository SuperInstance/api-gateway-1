"""Rate limiting algorithms — token bucket, sliding window, fixed window."""

from __future__ import annotations

import math
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class RateLimitResult:
    """Outcome of a rate-limit check."""

    allowed: bool
    remaining: int = 0
    retry_after: float | None = None


class RateLimiter(ABC):
    """Abstract base for rate-limiting strategies."""

    @abstractmethod
    def allow(self, key: str) -> RateLimitResult:
        ...


class TokenBucketLimiter(RateLimiter):
    """Token-bucket rate limiter.

    * ``rate`` — tokens added per second
    * ``capacity`` — maximum burst size
    """

    def __init__(self, rate: float = 10.0, capacity: int = 20) -> None:
        self.rate = rate
        self.capacity = capacity
        self._buckets: dict[str, tuple[float, float]] = {}  # key → (tokens, last_refill)

    def allow(self, key: str) -> RateLimitResult:
        now = time.monotonic()
        tokens, last = self._buckets.get(key, (float(self.capacity), now))
        elapsed = now - last
        tokens = min(self.capacity, tokens + elapsed * self.rate)

        if tokens >= 1.0:
            tokens -= 1.0
            self._buckets[key] = (tokens, now)
            return RateLimitResult(allowed=True, remaining=int(tokens))
        else:
            retry = (1.0 - tokens) / self.rate
            self._buckets[key] = (tokens, now)
            return RateLimitResult(allowed=False, remaining=0, retry_after=retry)


class FixedWindowLimiter(RateLimiter):
    """Fixed-window rate limiter.

    * ``limit`` — max requests per window
    * ``window_seconds`` — window duration
    """

    def __init__(self, limit: int = 100, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._windows: dict[str, tuple[int, float]] = {}  # key → (count, window_start)

    def allow(self, key: str) -> RateLimitResult:
        now = time.monotonic()
        count, window_start = self._windows.get(key, (0, now))

        if now - window_start >= self.window_seconds:
            count = 0
            window_start = now

        if count < self.limit:
            count += 1
            self._windows[key] = (count, window_start)
            return RateLimitResult(allowed=True, remaining=self.limit - count)
        else:
            retry = self.window_seconds - (now - window_start)
            self._windows[key] = (count, window_start)
            return RateLimitResult(allowed=False, remaining=0, retry_after=retry)


class SlidingWindowLimiter(RateLimiter):
    """Sliding-window (log-based) rate limiter.

    * ``limit`` — max requests per window
    * ``window_seconds`` — window duration
    """

    def __init__(self, limit: int = 100, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._logs: dict[str, list[float]] = {}

    def allow(self, key: str) -> RateLimitResult:
        now = time.monotonic()
        timestamps = self._logs.get(key, [])

        # Prune old entries
        cutoff = now - self.window_seconds
        timestamps = [t for t in timestamps if t > cutoff]

        if len(timestamps) < self.limit:
            timestamps.append(now)
            self._logs[key] = timestamps
            return RateLimitResult(allowed=True, remaining=self.limit - len(timestamps))
        else:
            oldest = timestamps[0]
            self._logs[key] = timestamps
            return RateLimitResult(
                allowed=False,
                remaining=0,
                retry_after=oldest + self.window_seconds - now,
            )
