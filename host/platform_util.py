#!/usr/bin/env python3
"""Minimal platform selection helpers for host runtime."""

from __future__ import annotations

import sys

_SELECTED_PLATFORM: str | None = None


def detect_platform() -> str:
    """Return detected platform backend name."""
    if sys.platform.startswith("win"):
        return "windows"
    return "mac"


def configure_platform(requested: str) -> str:
    """Configure selected platform from CLI flag and return resolved value."""
    global _SELECTED_PLATFORM
    normalized = requested.strip().lower()
    if normalized not in ("auto", "mac", "windows"):
        raise ValueError(f"unsupported platform flag: {requested}")
    _SELECTED_PLATFORM = detect_platform() if normalized == "auto" else normalized
    return _SELECTED_PLATFORM


def get_selected_platform() -> str:
    """Get selected platform (auto-detect if not configured)."""
    global _SELECTED_PLATFORM
    if _SELECTED_PLATFORM is None:
        _SELECTED_PLATFORM = detect_platform()
    return _SELECTED_PLATFORM


def is_windows() -> bool:
    return get_selected_platform() == "windows"


def is_mac() -> bool:
    return get_selected_platform() == "mac"
