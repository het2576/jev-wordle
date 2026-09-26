"""Per-IP sliding-window rate limiting as a FastAPI dependency.

Same pattern as Jev Sweeper. Each route gets its own bucket, so the cheap
routes can't use up the budget of the one that spends upstream calls
(/api/next-guess).
"""

from __future__ import annotations

import math
import os
import threading
import time
from collections import deque

from fastapi import HTTPException, Request

TRUST_PROXY = os.getenv("TRUST_PROXY_HEADERS", "0") == "1"


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_s: float = 60.0) -> None:
        self.limit = limit
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._last_sweep = time.monotonic()

    def hit(self, key: str) -> tuple[bool, int]:
        """Record a hit. Returns (allowed, seconds until the next free slot)."""
        now = time.monotonic()
        with self._lock:
            self._sweep(now)
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self.window_s:
                hits.popleft()
            if len(hits) >= self.limit:
                return False, max(1, math.ceil(self.window_s - (now - hits[0])))
            hits.append(now)
            return True, 0

    def _sweep(self, now: float) -> None:
        # Drop idle IPs now and then so memory doesn't grow forever.
        if now - self._last_sweep < self.window_s:
            return
        self._last_sweep = now
        for key in [k for k, v in self._hits.items() if not v or now - v[-1] >= self.window_s]:
            del self._hits[key]


def client_ip(request: Request) -> str:
    if TRUST_PROXY:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(name: str, default_per_minute: int):
    """Dependency factory: `Depends(rate_limit("next_guess", 30))`.

    Override any bucket with an env var, e.g. RATE_LIMIT_NEXT_GUESS=20.
    """
    limiter = SlidingWindowLimiter(int(os.getenv(f"RATE_LIMIT_{name.upper()}", default_per_minute)))

    def dependency(request: Request) -> None:
        allowed, retry_after = limiter.hit(client_ip(request))
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Too many requests. Try again in {retry_after}s.",
                headers={"Retry-After": str(retry_after)},
            )

    dependency.limiter = limiter  # exposed for tests
    return dependency
