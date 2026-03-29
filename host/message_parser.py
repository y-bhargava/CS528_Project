#!/usr/bin/env python3
"""NDJSON parsing helpers for host events."""

import json
import sys
from typing import Any


def parse_ndjson_line(raw_line: str, line_number: int) -> dict[str, Any] | None:
    """Parse one NDJSON line into a message object or return None."""
    line = raw_line.strip()
    if not line:
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
