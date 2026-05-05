#!/usr/bin/env python3
"""Gesture routing from low-level gesture names to semantic actions."""

from dataclasses import dataclass
from typing import Optional

GESTURE_TO_ACTION = {
    "left": "PREV_TAB",
    "right": "NEXT_TAB",
    "up": "PAGE_UP",
    "down": "PAGE_DOWN",
    "twist": "TOGGLE_PAUSE",
    # Backward-compat aliases while teams migrate labels.
    "swipe_left": "PREV_TAB",
    "swipe_right": "NEXT_TAB",
    "flick_up": "PAGE_UP",
    "flick_down": "PAGE_DOWN",
    "twist": "TOGGLE_PAUSE"
}


def route_gesture(name: str) -> Optional[str]:
    """Return the semantic action for a gesture name, or None if unmapped."""
    return GESTURE_TO_ACTION.get(name)


APP_ALIASES: dict[str, str] = {
    "Google Chrome": "chrome",
    "Brave Browser": "chrome",
    "Keynote": "presentation",
    "Microsoft PowerPoint": "presentation",
    "Spotify": "spotify",
}

PROFILE_MAPPINGS: dict[str, dict[str, str]] = {
    "chrome": {
        "left": "PREV_TAB",
        "right": "NEXT_TAB",
        "up": "NEW_TAB",
        "down": "CLOSE_TAB",
    },
    "presentation": {
        "left": "PREV_SLIDE",
        "right": "NEXT_SLIDE",
        "up": "START_PRESENTATION",
        "down": "EXIT_PRESENTATION",
    },
    "spotify": {
        "left": "PREV_TRACK",
        "right": "NEXT_TRACK",
        "up": "VOLUME_UP",
        "down": "VOLUME_DOWN",
    },
    "desktop": {
        "left": "SWITCH_SPACE_LEFT",
        "right": "SWITCH_SPACE_RIGHT",
        "up": "MISSION_CONTROL",
        "down": "SHOW_DESKTOP",
    },
}


@dataclass(frozen=True)
class RouteResolution:
    action: Optional[str]
    profile: str


def resolve_profile(active_app_name: str | None, mode: str) -> str:
    """Choose a mapping profile from active app + mode."""
    normalized_mode = mode.strip().lower()
    if normalized_mode == "global":
        return "desktop"

    if active_app_name is None:
        return "desktop"
    return APP_ALIASES.get(active_app_name, "desktop")


def route_gesture_for_context(
    gesture_name: str,
    active_app_name: str | None,
    mode: str,
) -> RouteResolution:
    """Resolve action from gesture using app-aware routing profile."""
    profile = resolve_profile(active_app_name=active_app_name, mode=mode)
    action = PROFILE_MAPPINGS.get(profile, {}).get(gesture_name)
    return RouteResolution(action=action, profile=profile)
