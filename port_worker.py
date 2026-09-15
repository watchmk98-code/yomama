"""Serial background execution cycles, independent of connected browsers.

The server supplies the callback and owns its database, network and account
checks. Importing this module creates no threads and performs no I/O.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from typing import Callable, Optional


_LOG = logging.getLogger(__name__)


class PortExecutionWorker:
    """Run a bounded callback immediately and on monotonic polling deadlines.

    ``wake`` coalesces requests for another cycle. A wake during a callback runs
    the next cycle as soon as that callback returns; callbacks never overlap.
    The daemon flag only protects process exit if a callback exceeds its budget.
    Normal shutdown should call ``stop`` and inspect its boolean result.
    """

    def __init__(
        self, process_callback: Callable[[], object], poll_seconds: float = 2.0
    ) -> None:
        if not callable(process_callback):
            raise TypeError("process_callback must be callable")
        interval = float(poll_seconds)
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError("poll_seconds must be finite and greater than zero")
        self._process = process_callback
        self._interval = interval
        self._lifecycle_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()

    def start(self) -> bool:
        """Start once; return false if the previous run is still alive."""
        with self._lifecycle_lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            # Each run keeps its own events, including when restarted after a
            # completed stop. A concurrent stop cannot signal the new run.
            stop_event = threading.Event()
            wake_event = threading.Event()
            thread = threading.Thread(
                target=self._run,
                args=(stop_event, wake_event),
                name="port-execution",
                daemon=True,
            )
            self._stop_event = stop_event
            self._wake_event = wake_event
            self._thread = thread
            thread.start()
            return True

    def wake(self) -> None:
        """Request a prompt cycle without starting another execution thread."""
        with self._lifecycle_lock:
            if self._thread is not None and self._thread.is_alive():
                self._wake_event.set()

    def stop(self, timeout: float = 20.0) -> bool:
        """Signal shutdown and wait for the current bounded cycle to finish.

        Return false and log a fixed warning if the callback remains active
        after ``timeout`` seconds. Further ``stop`` calls can wait again.
        """
        wait_seconds = float(timeout)
        if not math.isfinite(wait_seconds) or wait_seconds < 0:
            raise ValueError("timeout must be finite and nonnegative")
        with self._lifecycle_lock:
            thread = self._thread
            if thread is None:
                return True
            self._stop_event.set()
            self._wake_event.set()
        # A callback may request its own shutdown; it cannot join itself.
        if thread is threading.current_thread():
            _LOG.warning("PORT execution worker cannot wait for its own cycle.")
            return False
        thread.join(wait_seconds)
        if thread.is_alive():
            _LOG.warning("PORT execution worker did not stop before its timeout.")
            return False
        return True

    def _run(
        self, stop_event: threading.Event, wake_event: threading.Event
    ) -> None:
        next_cycle = time.monotonic()
        while not stop_event.is_set():
            wake_event.wait(max(0.0, next_cycle - time.monotonic()))
            if stop_event.is_set():
                break
            # Requests received before the cycle are handled by this cycle;
            # requests received during it remain set for the next iteration.
            wake_event.clear()
            started = time.monotonic()
            try:
                self._process()
            except Exception:
                # Provider exception messages may contain account information.
                # Do not attach exception details, arguments or a traceback.
                _LOG.warning("PORT execution cycle failed; a later cycle will retry.")
            next_cycle = started + self._interval
            now = time.monotonic()
            if next_cycle <= now:
                # Skip missed deadlines rather than immediately replaying a
                # backlog of cycles after a slow provider response.
                missed = math.floor((now - next_cycle) / self._interval) + 1
                next_cycle += missed * self._interval
