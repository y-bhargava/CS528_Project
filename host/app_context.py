#!/usr/bin/env python3
"""Frontmost app detection helpers."""

import subprocess


def get_frontmost_app_name() -> str | None:
    """Return frontmost process name, or None when unavailable."""
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
