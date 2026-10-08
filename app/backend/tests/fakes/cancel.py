"""A stop signal with the shape of the analysis engine's cancellation token.

``cancel`` may be called from any thread; hooks run once, at once when already cancelled.
"""

import threading
from collections.abc import Callable


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._hooks: dict[int, Callable[[], None]] = {}
        self._next = 0

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        with self._lock:
            if self._event.is_set():
                return
            self._event.set()
            hooks = list(self._hooks.values())
            self._hooks.clear()
        for hook in hooks:
            hook()

    def on_cancel(self, hook: Callable[[], None]) -> Callable[[], None]:
        with self._lock:
            if not self._event.is_set():
                key, self._next = self._next, self._next + 1
                self._hooks[key] = hook

                def unregister() -> None:
                    with self._lock:
                        self._hooks.pop(key, None)

                return unregister
        hook()
        return lambda: None
