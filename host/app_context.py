#!/usr/bin/env python3
"""Frontmost app detection helpers."""

import csv
import subprocess
from io import StringIO

from platform_util import is_windows


def _get_frontmost_app_name_mac() -> str | None:
    script = (
        'tell application "System Events" to '
        "name of first application process whose frontmost is true"
    )
    result = subprocess.run(
        ["osascript", "-e", script],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    name = result.stdout.strip()
    return name or None


def _get_foreground_pid_windows() -> int | None:
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return None

    if not hasattr(ctypes, "windll"):
        return None

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if hwnd == 0:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == 0:
        return None
    return int(pid.value)


def _get_process_name_windows(pid: int) -> str | None:
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    line = result.stdout.strip()
    if not line or line.startswith("INFO:"):
        return None
    try:
        row = next(csv.reader(StringIO(line)))
    except Exception:
        return None
    if not row:
        return None
    name = row[0].strip()
    return name or None


def _get_frontmost_app_name_windows() -> str | None:
    pid = _get_foreground_pid_windows()
    if pid is None:
        return None
    return _get_process_name_windows(pid)


def get_frontmost_app_name() -> str | None:
    """Return frontmost process name, or None when unavailable."""
    if is_windows():
        return _get_frontmost_app_name_windows()
    return _get_frontmost_app_name_mac()
