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
    "CLOSE_TAB": 0.35,
    "PLAY_PAUSE": 1.00,
    "PREV_SLIDE": 0.30,
    "NEXT_SLIDE": 0.30,
    "START_PRESENTATION": 0.80,
    "EXIT_PRESENTATION": 0.80,
    "PREV_TRACK": 0.40,
    "NEXT_TRACK": 0.40,
    "VOLUME_UP": 0.20,
    "VOLUME_DOWN": 0.20,
    "SWITCH_SPACE_LEFT": 0.85,
    "SWITCH_SPACE_RIGHT": 0.85,
    "MISSION_CONTROL": 0.85,
    "SHOW_DESKTOP": 0.85,
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


def _run_close_tab() -> None:
    pyautogui = _get_pyautogui()
    pyautogui.hotkey("command", "w")


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


def _run_prev_slide() -> None:
    pyautogui = _get_pyautogui()
    pyautogui.press("up")


def _run_next_slide() -> None:
    pyautogui = _get_pyautogui()
    pyautogui.press("down")


def _get_frontmost_app_name() -> str | None:
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


def _run_start_presentation() -> None:
    pyautogui = _get_pyautogui()
    app_name = _get_frontmost_app_name()
    if app_name == "Keynote":
        pyautogui.hotkey("command", "option", "p")
        return
    if app_name == "Microsoft PowerPoint":
        pyautogui.hotkey("shift", "f5")
        return
    # Conservative fallback when app detection is unavailable.
    pyautogui.hotkey("command", "option", "p")


def _run_exit_presentation() -> None:
    pyautogui = _get_pyautogui()
    pyautogui.press("esc")


def _run_spotify_next_track() -> None:
    result = subprocess.run(
        ["osascript", "-e", 'tell application "Spotify" to next track'],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"osascript failed rc={result.returncode}")


def _run_spotify_prev_track() -> None:
    result = subprocess.run(
        ["osascript", "-e", 'tell application "Spotify" to previous track'],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"osascript failed rc={result.returncode}")


def _run_volume_up() -> None:
    result = subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "Spotify" to set v to sound volume',
            "-e",
            "set v to v + 20",
            "-e",
            "if v > 100 then set v to 100",
            "-e",
            'tell application "Spotify" to set sound volume to v',
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"osascript failed rc={result.returncode}")


def _run_volume_down() -> None:
    result = subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "Spotify" to set v to sound volume',
            "-e",
            "set v to v - 20",
            "-e",
            "if v < 0 then set v to 0",
            "-e",
            'tell application "Spotify" to set sound volume to v',
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"osascript failed rc={result.returncode}")


def _run_switch_space_left() -> None:
    pyautogui = _get_pyautogui()
    pyautogui.hotkey("ctrl", "left")


def _run_switch_space_right() -> None:
    pyautogui = _get_pyautogui()
    pyautogui.hotkey("ctrl", "right")


def _run_mission_control() -> None:
    pyautogui = _get_pyautogui()
    pyautogui.hotkey("ctrl", "up")


def _run_show_desktop() -> None:
    pyautogui = _get_pyautogui()
    pyautogui.hotkey("command", "f3")


ACTION_HANDLERS: dict[str, Callable[[], None]] = {
    "PREV_TAB": _run_prev_tab,
    "NEXT_TAB": _run_next_tab,
    "NEW_TAB": _run_new_tab,
    "CLOSE_TAB": _run_close_tab,
    "PLAY_PAUSE": _run_play_pause,
    "PREV_SLIDE": _run_prev_slide,
    "NEXT_SLIDE": _run_next_slide,
    "START_PRESENTATION": _run_start_presentation,
    "EXIT_PRESENTATION": _run_exit_presentation,
    "PREV_TRACK": _run_spotify_prev_track,
    "NEXT_TRACK": _run_spotify_next_track,
    "VOLUME_UP": _run_volume_up,
    "VOLUME_DOWN": _run_volume_down,
    "SWITCH_SPACE_LEFT": _run_switch_space_left,
    "SWITCH_SPACE_RIGHT": _run_switch_space_right,
    "MISSION_CONTROL": _run_mission_control,
    "SHOW_DESKTOP": _run_show_desktop,
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
