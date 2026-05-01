#!/usr/bin/env python3
"""Input source helpers for NDJSON streams."""

from typing import Iterator
import sys

try:
    import serial  # type: ignore
except Exception:
    serial = None  # type: ignore[assignment]


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
    """Yield NDJSON lines from a serial device."""
    if serial is None:
        raise RuntimeError(
            "pyserial is required for serial input. Install it with: "
            "python3 -m pip install pyserial"
        )

    try:
        with serial.Serial(port=port, baudrate=baud, timeout=0.5) as ser:
            while True:
                raw = ser.readline()
                if not raw:
                    continue
                yield raw.decode("utf-8", errors="replace")
    except serial.SerialException as exc:
        raise RuntimeError(
            f"failed to open/read serial port '{port}' at {baud} baud: {exc}"
        ) from exc
