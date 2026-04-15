#!/usr/bin/env python3
"""Emit simulated gesture messages as NDJSON."""

import json
import random
import signal
import time

GESTURES = ["up", "down", "left", "right"]
DELAY_SECONDS = 0.5


def main() -> None:
    while True:
        message = {
            "type": "gesture",
            "name": random.choice(GESTURES),
            "source": "simulator",
        }
        try:
            print(json.dumps(message, separators=(",", ":")), flush=True)
        except BrokenPipeError:
            # Downstream consumer closed the pipe; exit quietly.
            return
        time.sleep(DELAY_SECONDS)


if __name__ == "__main__":
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    try:
        main()
    except KeyboardInterrupt:
        pass
