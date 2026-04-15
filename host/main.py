#!/usr/bin/env python3
"""Orchestrate host event flow: input -> parse -> route -> execute."""

import argparse
import signal
import sys
import time
from typing import Iterable

from executor import execute_action
from input_sources import (
    iter_ndjson_file,
    iter_ndjson_serial,
    iter_ndjson_stdin,
)
from message_parser import parse_ndjson_line
from router import route_gesture


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Touchless HCI host listener")
    parser.add_argument(
        "--input-file",
        help="Read NDJSON messages from a replay file instead of stdin.",
    )
    parser.add_argument(
        "--serial-port",
        help="Read NDJSON messages from a serial port.",
    )
    parser.add_argument(
        "--serial-baud",
        type=int,
        default=115200,
        help="Baud rate for serial input (default: 115200).",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run executor in live mode. Default is dry-run.",
    )
    return parser


def _select_input_lines(args: argparse.Namespace) -> Iterable[str]:
    if args.input_file and args.serial_port:
        raise ValueError("Use either --input-file or --serial-port, not both.")

    if args.serial_port:
        return iter_ndjson_serial(args.serial_port, args.serial_baud)
    if args.input_file:
        return iter_ndjson_file(args.input_file)
    return iter_ndjson_stdin()


def _announce_live_mode() -> None:
    print(
        "[live] LIVE MODE ENABLED: real macOS actions may be executed",
        flush=True,
    )
    for seconds in range(3, 0, -1):
        print(f"[live] starting in {seconds}...", flush=True)
        time.sleep(1)
    print("[live] live execution active", flush=True)


def main() -> int:
    args = _build_arg_parser().parse_args()
    dry_run = not args.live

    try:
        lines = _select_input_lines(args)
    except ValueError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2
    except NotImplementedError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.live:
        _announce_live_mode()

    try:
        for line_number, raw_line in enumerate(lines, start=1):
            message = parse_ndjson_line(raw_line, line_number)
            if message is None:
                continue

            message_type = message.get("type", "<missing>")
            if message_type == "gesture":
                name = message.get("name")
                if isinstance(name, str) and name.strip():
                    gesture_name = name.strip()
                    action = route_gesture(gesture_name)
                    if action is not None:
                        print(f"type=gesture name={gesture_name} action={action}")
                        execute_action(action, dry_run=dry_run)
                    else:
                        print(f"type=gesture name={gesture_name} action=<unmapped>")
                        print(
                            f"[warning] line={line_number} unknown gesture name={gesture_name}",
                            file=sys.stderr,
                        )
                else:
                    print("type=gesture name=<missing>")
                    print(
                        f"[warning] line={line_number} gesture message missing name",
                        file=sys.stderr,
                    )
            else:
                print(f"type={message_type}")
    except (RuntimeError, NotImplementedError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        # Downstream consumer closed the pipe; exit quietly.
        try:
            sys.stdout.close()
        except OSError:
            pass
        raise SystemExit(0)
    except KeyboardInterrupt:
        raise SystemExit(0)
