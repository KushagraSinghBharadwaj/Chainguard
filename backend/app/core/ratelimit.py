import threading
import time
from collections.abc import Callable


class TokenBucket:
    """In-process token bucket (single-process dev setup; see DATABASE_SCHEMA.md).

    The clock is injectable so tests can control time without sleeping.
    """

    def __init__(
        self,
        capacity: int,
        refill_per_second: float,
        max_keys: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._capacity = float(capacity)
        self._rate = refill_per_second
        self._max_keys = max_keys
        self._clock = clock
        self._state: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, float]:
        """Return (allowed, retry_after_seconds)."""
        now = self._clock()
        with self._lock:
            tokens, last = self._state.get(key, (self._capacity, now))
            tokens = min(self._capacity, tokens + (now - last) * self._rate)
            if tokens >= 1:
                self._state[key] = (tokens - 1, now)
                allowed, retry = True, 0.0
            else:
                self._state[key] = (tokens, now)
                allowed, retry = False, (1 - tokens) / self._rate
            if len(self._state) > self._max_keys:
                full_after = self._capacity / self._rate
                self._state = {
                    k: v for k, v in self._state.items() if now - v[1] < full_after
                }
        return allowed, retry

    def reset(self) -> None:
        with self._lock:
            self._state.clear()
