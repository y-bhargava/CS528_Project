#!/usr/bin/env python3
"""Background frontmost-app polling with thread-safe cached reads."""

from __future__ import annotations

import threading
import time

from app_context import get_frontmost_app_name


class FrontmostAppMonitor:
    """Poll frontmost app on a background thread and cache latest value."""

    def __init__(self, poll_interval_seconds: float = 1.0) -> None:
        self._poll_interval_seconds = max(0.2, float(poll_interval_seconds))
        self._lock = threading.Lock()
        self._latest: str | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="frontmost-app-monitor",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout_seconds: float = 1.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(0.1, timeout_seconds))

    def get_latest(self) -> str | None:
        with self._lock:
            return self._latest

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                value = get_frontmost_app_name()
            except Exception:
                value = None
            with self._lock:
                self._latest = value
            self._stop_event.wait(self._poll_interval_seconds)
