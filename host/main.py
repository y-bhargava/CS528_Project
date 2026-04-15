#!/usr/bin/env python3
"""Orchestrate host event flow: input -> parse -> route -> execute."""

import argparse
import signal
import sys
import threading
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
        "--mode",
        choices=("esp", "cv", "hybrid"),
        default="esp",
        help="Input mode: esp, cv, or hybrid (default: esp).",
    )
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
        help="Run in live mode. Default is dry-run.",
    )
    parser.add_argument(
        "--camera-index",
        type=int,
        default=0,
        help="OpenCV camera index for CV modes (default: 0).",
    )
    parser.add_argument(
        "--smooth",
        type=float,
        default=0.22,
        help="CV cursor smoothing factor in [0,1] (default: 0.22).",
    )
    parser.add_argument(
        "--pinch-threshold",
        type=float,
        default=0.045,
        help="CV pinch threshold (default: 0.045).",
    )
    parser.add_argument(
        "--drag-hold-ms",
        type=int,
        default=350,
        help="CV hold time in ms before drag starts (default: 350).",
    )
    parser.add_argument(
        "--click-move-threshold",
        type=float,
        default=24.0,
        help="Max cursor drift in px for pinch-click (default: 24).",
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


def _handle_gesture(gesture_name: str, dry_run: bool, line_number: int) -> None:
    action = route_gesture(gesture_name)
    if action is not None:
        print(f"type=gesture name={gesture_name} action={action}", flush=True)
        execute_action(action, dry_run=dry_run)
    else:
        print(f"type=gesture name={gesture_name} action=<unmapped>", flush=True)
        print(
            f"[warning] line={line_number} unknown gesture name={gesture_name}",
            file=sys.stderr,
            flush=True,
        )


def _run_esp_pipeline(args: argparse.Namespace, dry_run: bool, stop_event: threading.Event | None = None) -> int:
    try:
        lines = _select_input_lines(args)
    except ValueError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2
    except NotImplementedError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        for line_number, raw_line in enumerate(lines, start=1):
            if stop_event is not None and stop_event.is_set():
                break
            message = parse_ndjson_line(raw_line, line_number)
            if message is None:
                continue

            message_type = message.get("type", "<missing>")
            if message_type == "gesture":
                name = message.get("name")
                if isinstance(name, str) and name.strip():
                    gesture_name = name.strip()
                    _handle_gesture(gesture_name, dry_run=dry_run, line_number=line_number)
                else:
                    print("type=gesture name=<missing>", flush=True)
                    print(
                        f"[warning] line={line_number} gesture message missing name",
                        file=sys.stderr,
                        flush=True,
                    )
            else:
                print(f"type={message_type}", flush=True)
    except (RuntimeError, NotImplementedError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2

    return 0


def _build_cv_config(args: argparse.Namespace, dry_run: bool):
    from cv_cursor import CVCursorConfig

    return CVCursorConfig(
        camera_index=args.camera_index,
        smooth=args.smooth,
        pinch_threshold=args.pinch_threshold,
        drag_hold_ms=args.drag_hold_ms,
        click_move_threshold=args.click_move_threshold,
        dry_run=dry_run,
        show_window=True,
        window_title="HCI Cursor (q to quit)",
    )


def main() -> int:
    args = _build_arg_parser().parse_args()
    dry_run = not args.live

    if args.live:
        _announce_live_mode()

    if args.mode == "esp":
        return _run_esp_pipeline(args, dry_run=dry_run)

    if args.mode == "cv":
        from cv_cursor import run_cv_cursor

        return run_cv_cursor(_build_cv_config(args, dry_run=dry_run))

    if not args.serial_port and not args.input_file:
        print(
            "[error] hybrid mode requires --serial-port or --input-file for ESP input",
            file=sys.stderr,
        )
        return 2

    stop_event = threading.Event()
    esp_result = {"code": 0}

    def _esp_worker() -> None:
        esp_result["code"] = _run_esp_pipeline(args, dry_run=dry_run, stop_event=stop_event)
        stop_event.set()

    esp_thread = threading.Thread(target=_esp_worker, name="esp-listener", daemon=True)
    esp_thread.start()
    from cv_cursor import run_cv_cursor

    cv_code = 0
    try:
        cv_code = run_cv_cursor(_build_cv_config(args, dry_run=dry_run), stop_event=stop_event)
    finally:
        stop_event.set()
        esp_thread.join(timeout=2.0)

    if esp_result["code"] != 0:
        return int(esp_result["code"])
    return cv_code


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
