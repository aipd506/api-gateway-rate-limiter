"""High-Throughput Rate Limiting Algorithms.

Implements Token Bucket, Leaky Bucket, Sliding Window Counter, and Sliding Window Log.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset: int
    retry_after: int
    policy: str
    current_usage: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "limit": self.limit,
            "remaining": self.remaining,
            "reset": self.reset,
            "retry_after": self.retry_after,
            "policy": self.policy,
            "current_usage": self.current_usage,
        }


class TokenBucket:
    """Token Bucket rate limiter with continuous burst refill."""

    def __init__(
        self,
        capacity: float = 10.0,
        refill_rate: float = 1.0,
        initial_tokens: float | None = None,
        now: float | None = None,
    ) -> None:
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate)
        self.tokens = self.capacity if initial_tokens is None else float(initial_tokens)
        self.last_refill = time.time() if now is None else float(now)
        self._lock = threading.Lock()

    def allow(self, cost: int = 1, now: float | None = None) -> RateLimitResult:
        current_time = time.time() if now is None else float(now)
        with self._lock:
            # Check if cost exceeds total capacity immediately (Edge Case #26)
            if cost > self.capacity:
                wait_sec = math.ceil(self.capacity / max(self.refill_rate, 0.001))
                return RateLimitResult(
                    allowed=False,
                    limit=int(self.capacity),
                    remaining=int(self.tokens),
                    reset=wait_sec,
                    retry_after=wait_sec,
                    policy=f"{int(self.capacity)};w=60;burst={int(self.capacity)}",
                    current_usage=self.capacity - self.tokens,
                )

            # Refill tokens
            elapsed = max(0.0, current_time - self.last_refill)
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = current_time

            if self.tokens >= cost:
                self.tokens -= cost
                reset_sec = math.ceil((self.capacity - self.tokens) / max(self.refill_rate, 0.001))
                return RateLimitResult(
                    allowed=True,
                    limit=int(self.capacity),
                    remaining=int(self.tokens),
                    reset=reset_sec,
                    retry_after=0,
                    policy=f"{int(self.capacity)};w=60;burst={int(self.capacity)}",
                    current_usage=self.capacity - self.tokens,
                )
            else:
                needed = cost - self.tokens
                wait_sec = math.ceil(needed / max(self.refill_rate, 0.001))
                return RateLimitResult(
                    allowed=False,
                    limit=int(self.capacity),
                    remaining=int(self.tokens),
                    reset=wait_sec,
                    retry_after=wait_sec,
                    policy=f"{int(self.capacity)};w=60;burst={int(self.capacity)}",
                    current_usage=self.capacity - self.tokens,
                )

    def inspect(self, now: float | None = None) -> dict[str, Any]:
        current_time = time.time() if now is None else float(now)
        with self._lock:
            elapsed = max(0.0, current_time - self.last_refill)
            cur_tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            return {
                "algorithm": "token_bucket",
                "capacity": self.capacity,
                "refill_rate": self.refill_rate,
                "current_tokens": cur_tokens,
                "last_refill": self.last_refill,
            }

    def reset(self, now: float | None = None) -> None:
        with self._lock:
            self.tokens = self.capacity
            self.last_refill = time.time() if now is None else float(now)


class LeakyBucket:
    """Leaky Bucket rate limiter with constant rate traffic smoothing."""

    def __init__(
        self,
        capacity: float = 10.0,
        leak_rate: float = 1.0,
        now: float | None = None,
    ) -> None:
        self.capacity = float(capacity)
        self.leak_rate = float(leak_rate)
        self.water = 0.0
        self.last_leak = time.time() if now is None else float(now)
        self._lock = threading.Lock()

    def allow(self, cost: int = 1, now: float | None = None) -> RateLimitResult:
        current_time = time.time() if now is None else float(now)
        with self._lock:
            # Leak water
            elapsed = max(0.0, current_time - self.last_leak)
            self.water = max(0.0, self.water - elapsed * self.leak_rate)
            self.last_leak = current_time

            if self.water + cost <= self.capacity:
                self.water += cost
                remaining = int(max(0, self.capacity - self.water))
                reset_sec = math.ceil(self.water / max(self.leak_rate, 0.001))
                return RateLimitResult(
                    allowed=True,
                    limit=int(self.capacity),
                    remaining=remaining,
                    reset=reset_sec,
                    retry_after=0,
                    policy=f"{int(self.capacity)};w=60;burst={int(self.capacity)}",
                    current_usage=self.water,
                )
            else:
                overflow = (self.water + cost) - self.capacity
                wait_sec = math.ceil(overflow / max(self.leak_rate, 0.001))
                remaining = int(max(0, self.capacity - self.water))
                return RateLimitResult(
                    allowed=False,
                    limit=int(self.capacity),
                    remaining=remaining,
                    reset=wait_sec,
                    retry_after=wait_sec,
                    policy=f"{int(self.capacity)};w=60;burst={int(self.capacity)}",
                    current_usage=self.water,
                )

    def inspect(self, now: float | None = None) -> dict[str, Any]:
        current_time = time.time() if now is None else float(now)
        with self._lock:
            elapsed = max(0.0, current_time - self.last_leak)
            cur_water = max(0.0, self.water - elapsed * self.leak_rate)
            return {
                "algorithm": "leaky_bucket",
                "capacity": self.capacity,
                "leak_rate": self.leak_rate,
                "water_level": cur_water,
                "last_leak": self.last_leak,
            }

    def reset(self, now: float | None = None) -> None:
        with self._lock:
            self.water = 0.0
            self.last_leak = time.time() if now is None else float(now)


class SlidingWindowCounter:
    """Sliding Window Counter using weighted interpolation between adjacent time windows."""

    def __init__(
        self,
        limit: int = 60,
        window_seconds: float = 60.0,
        now: float | None = None,
    ) -> None:
        self.limit = int(limit)
        self.window_seconds = float(window_seconds)
        self.prev_count = 0.0
        self.curr_count = 0.0
        self.window_start = time.time() if now is None else float(now)
        self._lock = threading.Lock()

    def allow(self, cost: int = 1, now: float | None = None) -> RateLimitResult:
        current_time = time.time() if now is None else float(now)
        with self._lock:
            elapsed = current_time - self.window_start

            if elapsed >= 2 * self.window_seconds:
                self.prev_count = 0.0
                self.curr_count = 0.0
                self.window_start = current_time
                elapsed = 0.0
            elif elapsed >= self.window_seconds:
                self.prev_count = self.curr_count
                self.curr_count = 0.0
                self.window_start += self.window_seconds
                elapsed = current_time - self.window_start

            # Weighted interpolation (Edge Case #27)
            weight = max(0.0, min(1.0, (self.window_seconds - elapsed) / self.window_seconds))
            estimated_count = self.curr_count + (self.prev_count * weight)

            if estimated_count + cost <= self.limit:
                self.curr_count += cost
                remaining = int(max(0, self.limit - (estimated_count + cost)))
                reset_sec = math.ceil(self.window_seconds - elapsed)
                return RateLimitResult(
                    allowed=True,
                    limit=self.limit,
                    remaining=remaining,
                    reset=reset_sec,
                    retry_after=0,
                    policy=f"{self.limit};w={int(self.window_seconds)}",
                    current_usage=estimated_count + cost,
                )
            else:
                wait_sec = math.ceil(self.window_seconds - elapsed)
                remaining = int(max(0, self.limit - estimated_count))
                return RateLimitResult(
                    allowed=False,
                    limit=self.limit,
                    remaining=remaining,
                    reset=max(1, wait_sec),
                    retry_after=max(1, wait_sec),
                    policy=f"{self.limit};w={int(self.window_seconds)}",
                    current_usage=estimated_count,
                )

    def inspect(self, now: float | None = None) -> dict[str, Any]:
        current_time = time.time() if now is None else float(now)
        with self._lock:
            elapsed = current_time - self.window_start
            weight = max(0.0, min(1.0, (self.window_seconds - elapsed) / self.window_seconds))
            estimated = self.curr_count + (self.prev_count * weight)
            return {
                "algorithm": "sliding_window_counter",
                "limit": self.limit,
                "window_seconds": self.window_seconds,
                "estimated_count": estimated,
                "curr_count": self.curr_count,
                "prev_count": self.prev_count,
            }

    def reset(self, now: float | None = None) -> None:
        with self._lock:
            self.prev_count = 0.0
            self.curr_count = 0.0
            self.window_start = time.time() if now is None else float(now)


class SlidingWindowLog:
    """Sliding Window Log maintaining moving timestamp log with exact precision."""

    def __init__(
        self,
        limit: int = 60,
        window_seconds: float = 60.0,
    ) -> None:
        self.limit = int(limit)
        self.window_seconds = float(window_seconds)
        self.timestamps: list[float] = []
        self._lock = threading.Lock()

    def allow(self, cost: int = 1, now: float | None = None) -> RateLimitResult:
        current_time = time.time() if now is None else float(now)
        with self._lock:
            cutoff = current_time - self.window_seconds
            # Evict timestamps older than moving window
            self.timestamps = [t for t in self.timestamps if t >= cutoff]

            if len(self.timestamps) + cost <= self.limit:
                for _ in range(cost):
                    self.timestamps.append(current_time)
                remaining = self.limit - len(self.timestamps)
                oldest = self.timestamps[0]
                reset_sec = math.ceil(self.window_seconds - (current_time - oldest))
                return RateLimitResult(
                    allowed=True,
                    limit=self.limit,
                    remaining=remaining,
                    reset=max(1, reset_sec),
                    retry_after=0,
                    policy=f"{self.limit};w={int(self.window_seconds)}",
                    current_usage=len(self.timestamps),
                )
            else:
                oldest = self.timestamps[0] if self.timestamps else current_time
                wait_sec = math.ceil(self.window_seconds - (current_time - oldest))
                return RateLimitResult(
                    allowed=False,
                    limit=self.limit,
                    remaining=0,
                    reset=max(1, wait_sec),
                    retry_after=max(1, wait_sec),
                    policy=f"{self.limit};w={int(self.window_seconds)}",
                    current_usage=len(self.timestamps),
                )

    def inspect(self, now: float | None = None) -> dict[str, Any]:
        current_time = time.time() if now is None else float(now)
        with self._lock:
            cutoff = current_time - self.window_seconds
            active = [t for t in self.timestamps if t >= cutoff]
            return {
                "algorithm": "sliding_window_log",
                "limit": self.limit,
                "window_seconds": self.window_seconds,
                "active_requests": len(active),
            }

    def reset(self, now: float | None = None) -> None:
        with self._lock:
            self.timestamps.clear()


def create_limiter(
    algorithm: str,
    rate_or_limit: int = 60,
    burst_or_cap: int = 10,
    window_seconds: float = 60.0,
    now: float | None = None,
) -> TokenBucket | LeakyBucket | SlidingWindowCounter | SlidingWindowLog:
    """Factory creating limiter by algorithm name."""
    algo = algorithm.lower().replace("-", "_")
    if algo in ("token", "token_bucket"):
        refill_rate = rate_or_limit / max(1.0, window_seconds)
        capacity = burst_or_cap
        return TokenBucket(capacity=capacity, refill_rate=refill_rate, now=now)
    elif algo in ("leaky", "leaky_bucket"):
        leak_rate = rate_or_limit / max(1.0, window_seconds)
        capacity = burst_or_cap
        return LeakyBucket(capacity=capacity, leak_rate=leak_rate, now=now)
    elif algo in ("sliding", "sliding_window", "sliding_counter"):
        return SlidingWindowCounter(limit=rate_or_limit, window_seconds=window_seconds, now=now)
    elif algo in ("log", "sliding_log", "sliding_window_log"):
        return SlidingWindowLog(limit=rate_or_limit, window_seconds=window_seconds)
    else:
        raise ValueError(f"Unknown rate limiting algorithm: '{algorithm}'")
