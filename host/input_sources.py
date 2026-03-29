#!/usr/bin/env python3
"""Input source helpers for NDJSON streams."""

from typing import Iterator
import sys

SERIAL_NOT_IMPLEMENTED_MESSAGE = (
    "Serial input source is not implemented yet. "
    "Use stdin or file replay for now."
)


def iter_ndjson_stdin() -> Iterator[str]:
    """Yield NDJSON lines from stdin."""
    for line in sys.stdin:
        yield line


def iter_ndjson_file(path: str) -> Iterator[str]:
    """Yield NDJSON lines from a replay file."""
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            yield line


def iter_ndjson_serial(port: str, baud: int) -> Iterator[str]:
    """Placeholder serial source for future integration."""
    del port, baud
    raise NotImplementedError(SERIAL_NOT_IMPLEMENTED_MESSAGE)
