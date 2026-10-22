import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException


class RateLimiter:
    """In-memory sliding window. Per-process: fine for one container; use Redis to scale out."""

    def __init__(self):
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, key: str, limit: int, window: int = 60) -> None:
        now = time.monotonic()
        with self.lock:
            dq = self.hits[key]
            while dq and now - dq[0] >= window:
                dq.popleft()
            if len(dq) >= limit:
                retry = max(1, int(window - (now - dq[0])) + 1)
                raise HTTPException(429, f"Too many requests. Try again in {retry}s.",
                                    headers={"Retry-After": str(retry)})
            dq.append(now)
            if len(self.hits) > 10000:  # bound memory
                for k in [k for k, v in self.hits.items() if not v]:
                    del self.hits[k]


class SharedQuota:
    """Process-wide memory of whether Gemini has CONFIRMED the shared key's quota is exhausted.
    While exhausted we stop calling the provider (no point burning requests) until the cooldown ends."""

    def __init__(self):
        self.lock = threading.Lock()
        self.until = 0.0
        self.strikes = 0

    def exhausted(self) -> bool:
        with self.lock:
            return time.monotonic() < self.until

    def mark_exhausted(self, minutes: int) -> None:
        with self.lock:
            self.until = time.monotonic() + minutes * 60
            self.strikes = 0

    def strike(self, needed: int) -> bool:
        """Count an ambiguous 429; True once `needed` happen in a row."""
        with self.lock:
            self.strikes += 1
            return self.strikes >= needed

    def success(self) -> None:
        with self.lock:
            self.strikes = 0
            self.until = 0.0
