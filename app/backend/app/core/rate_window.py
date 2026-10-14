"""In-process sliding-window counters for request limits (application-foundation
003-anonymous-visitor Requirement 6).

Each key may be counted ``limit`` times within ``window_seconds``. The counters live in this
process (the backend runs as a single replica) and keep at most ``max_keys`` keys; the oldest key
is dropped first, so memory stays bounded whatever the callers send.
"""

import time
from collections import deque
from collections.abc import Callable, Hashable


class SlidingWindow:
    def __init__(
        self,
        *,
        limit: int,
        window_seconds: float,
        max_keys: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._max_keys = max_keys
        self._clock = clock
        self._hits: dict[Hashable, deque[float]] = {}

    def hit(self, key: Hashable) -> bool:
        """Count one request for ``key``; False (and nothing counted) when the limit is reached."""

        now = self._clock()
        seen = self._hits.pop(key, None) or deque()
        while seen and now - seen[0] >= self.window_seconds:
            seen.popleft()
        allowed = len(seen) < self.limit
        if allowed:
            seen.append(now)
        if seen:
            self._hits[key] = seen  # re-inserted: the most recently used key is the newest
            while len(self._hits) > self._max_keys:
                del self._hits[next(iter(self._hits))]
        return allowed

    def clear(self) -> None:
        self._hits.clear()
