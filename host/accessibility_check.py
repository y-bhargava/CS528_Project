#!/usr/bin/env python3
"""macOS accessibility trust checks for runtime process."""

from __future__ import annotations

import ctypes
from ctypes import c_bool


def _load_frameworks():
    framework_path = (
        "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
    )
    core_foundation_path = (
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
    )
    app_services = ctypes.cdll.LoadLibrary(framework_path)
    ctypes.cdll.LoadLibrary(core_foundation_path)
    return app_services


def is_process_trusted(prompt: bool = False) -> bool | None:
    """Return AX trust state on macOS, or None if check unavailable."""
    try:
        _ = prompt  # Caller may request prompt semantics; trust probing remains non-blocking.
        app_services = _load_frameworks()
        ax_is_trusted = app_services.AXIsProcessTrusted
        ax_is_trusted.restype = c_bool
        ax_is_trusted.argtypes = []
        return bool(ax_is_trusted())
    except Exception:
        return None
