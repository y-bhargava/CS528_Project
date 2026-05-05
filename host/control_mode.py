#!/usr/bin/env python3
"""Shared touchless control mode state."""

from dataclasses import dataclass
import threading


@dataclass(frozen=True)
class ModeSnapshot:
    mode: str


class ModeState:
    """Thread-safe mode state for routing policy."""

    def __init__(self) -> None:
        self._mode = "context"
        self._lock = threading.Lock()

    def get_mode(self) -> str:
        with self._lock:
            return self._mode

    def set_mode(self, mode: str) -> str:
        normalized = mode.strip().lower()
        if normalized not in ("context", "global"):
            raise ValueError(f"unsupported mode: {mode}")
        with self._lock:
            self._mode = normalized
            return self._mode

    def toggle(self) -> str:
        with self._lock:
            self._mode = "global" if self._mode == "context" else "context"
            return self._mode

    def snapshot(self) -> ModeSnapshot:
        with self._lock:
            return ModeSnapshot(mode=self._mode)
