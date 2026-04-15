#!/usr/bin/env python3
"""NDJSON parsing helpers for host events."""

import json
import sys
from typing import Any

_CMD_TO_GESTURE = {
    "UP": "up",
    "DOWN": "down",
    "LEFT": "left",
    "RIGHT": "right",
}


def parse_ndjson_line(raw_line: str, line_number: int) -> dict[str, Any] | None:
    """Parse one NDJSON line into a message object or return None."""
    line = raw_line.strip()
    if not line:
        return None

    if line.startswith("CMD:"):
        gesture = _CMD_TO_GESTURE.get(line[4:].strip().upper())
        if gesture is None:
            print(
                f"[parse-error] line={line_number} unknown_cmd={line}",
                file=sys.stderr,
            )
            return None
        return {"type": "gesture", "name": gesture, "source": "cmd_bridge"}

    # Ignore non-JSON serial chatter (boot logs, human-readable status lines).
    if not line.startswith("{"):
        return None

    try:
        message = json.loads(line)
    except json.JSONDecodeError as exc:
        print(
            f"[parse-error] line={line_number} error={exc.msg}",
            file=sys.stderr,
        )
        return None

    if not isinstance(message, dict):
        print(
            f"[parse-error] line={line_number} expected=object",
            file=sys.stderr,
        )
        return None

    return message
