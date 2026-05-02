#!/usr/bin/env python3
"""Gesture routing from low-level gesture names to semantic actions."""

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
