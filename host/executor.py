#!/usr/bin/env python3
"""Execute semantic actions for the host app."""

from typing import Callable
import subprocess
import sys
import time

LIVE_ACTION_COOLDOWNS: dict[str, float] = {
    "PREV_TAB": 0.35,
    "NEXT_TAB": 0.35,
    "NEW_TAB": 0.35,
    "PLAY_PAUSE": 1.00,
}

_LAST_LIVE_EXECUTION: dict[str, float] = {}
_PYAUTOGUI = None
_PYAUTOGUI_IMPORT_ERROR: Exception | None = None


def _get_pyautogui():
    """Import pyautogui lazily to keep dry-run dependency-free."""
    global _PYAUTOGUI, _PYAUTOGUI_IMPORT_ERROR
    if _PYAUTOGUI is not None:
        return _PYAUTOGUI
    if _PYAUTOGUI_IMPORT_ERROR is not None:
        raise RuntimeError("pyautogui is required for live tab actions")
    try:
        import pyautogui  # type: ignore
    except Exception as exc:
        _PYAUTOGUI_IMPORT_ERROR = exc
        raise RuntimeError("pyautogui is required for live tab actions") from exc
    _PYAUTOGUI = pyautogui
    return _PYAUTOGUI


def _run_prev_tab() -> None:
    pyautogui = _get_pyautogui()
    pyautogui.hotkey("command", "shift", "[")


def _run_next_tab() -> None:
    pyautogui = _get_pyautogui()
    pyautogui.hotkey("command", "shift", "]")


def _run_new_tab() -> None:
    pyautogui = _get_pyautogui()
    pyautogui.hotkey("command", "t")


def _run_play_pause() -> None:
    result = subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "System Events" to key code 100',
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"osascript failed rc={result.returncode}")


ACTION_HANDLERS: dict[str, Callable[[], None]] = {
    "PREV_TAB": _run_prev_tab,
    "NEXT_TAB": _run_next_tab,
    "NEW_TAB": _run_new_tab,
    "PLAY_PAUSE": _run_play_pause,
}


def execute_action(action: str, dry_run: bool = True) -> None:
    """Execute a semantic action or log it in dry-run mode."""
    handler = ACTION_HANDLERS.get(action)
    if handler is None:
        print(f"[warning] unknown action={action}", file=sys.stderr)
        return

    if dry_run:
        print(f"execute action={action} mode=dry_run")
        return

    now = time.monotonic()
    cooldown_seconds = LIVE_ACTION_COOLDOWNS.get(action, 0.0)
    last_execution = _LAST_LIVE_EXECUTION.get(action)
    if last_execution is not None and cooldown_seconds > 0:
        elapsed = now - last_execution
        remaining = cooldown_seconds - elapsed
        if remaining > 0:
            print(f"skip action={action} reason=cooldown remaining={remaining:.2f}")
            return

    try:
        handler()
        _LAST_LIVE_EXECUTION[action] = now
    except Exception as exc:
        print(f"[live-error] action={action} error={exc}", file=sys.stderr)
