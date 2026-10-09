"""Process-wide limit of concurrent chat requests (003-llm-connection Requirement 17).

Waiting calls get a slot in arrival order. A cancelled wait leaves the queue and never sends a
request. The limiter works across event loops and threads, so the analysis engine's thread, the
connection test and the measurement script share the same slots in one process.
"""

import asyncio
import threading
from collections import deque


class CallSlots:
    def __init__(self, limit: int) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        self._limit = limit
        self._lock = threading.Lock()
        self._active = 0
        self._waiters: deque[tuple[asyncio.AbstractEventLoop, asyncio.Future[None]]] = deque()

    @property
    def limit(self) -> int:
        return self._limit

    async def acquire(self) -> None:
        """Wait for a slot; on cancellation the caller holds none."""

        loop = asyncio.get_running_loop()
        with self._lock:
            if self._active < self._limit and not self._waiters:
                self._active += 1
                return
            future: asyncio.Future[None] = loop.create_future()
            waiter = (loop, future)
            self._waiters.append(waiter)
        try:
            await future
        except asyncio.CancelledError:
            with self._lock:
                try:
                    self._waiters.remove(waiter)
                    queued = True
                except ValueError:
                    queued = False
            # Granted while the cancellation arrived: hand the slot on.
            if not queued and future.done() and not future.cancelled():
                self.release()
            raise

    def release(self) -> None:
        with self._lock:
            if not self._waiters:
                self._active -= 1
                return
            loop, future = self._waiters.popleft()
        # The slot passes directly to the next waiter, so ``_active`` does not change.

        def grant() -> None:
            if future.cancelled():
                self.release()
            else:
                future.set_result(None)

        try:
            loop.call_soon_threadsafe(grant)
        except RuntimeError:  # the waiter's event loop is closed: the slot goes to the next one
            self.release()
