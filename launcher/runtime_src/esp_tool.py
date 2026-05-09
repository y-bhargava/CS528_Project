#!/usr/bin/env python3
"""Standalone ESP utility for flashing and stream verification.

This tool is designed to be bundled as a single executable and used by the
Electron launcher without requiring a separate Python installation on end-user
machines.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
from typing import Any

try:
    import esptool  # type: ignore
except Exception as exc:  # pragma: no cover - surfaced to caller
    print(f"[error] esptool unavailable: {exc}", file=sys.stderr, flush=True)
    raise

try:
    import serial  # type: ignore
except Exception as exc:  # pragma: no cover - surfaced to caller
    print(f"[error] pyserial unavailable: {exc}", file=sys.stderr, flush=True)
    raise


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Touchless ESP tooling")
    sub = parser.add_subparsers(dest="command", required=True)

    flash = sub.add_parser("flash", help="Flash ESP firmware from a manifest")
    flash.add_argument("--port", required=True, help="Serial port, e.g. /dev/cu.usbserial-10")
    flash.add_argument("--manifest", required=True, help="Path to firmware manifest JSON")
    flash.add_argument("--baud", type=int, default=460800, help="Flash baud rate (default: 460800)")

    verify_once = sub.add_parser("verify-once", help="Check for gesture NDJSON within a timeout")
    verify_once.add_argument("--port", required=True, help="Serial port")
    verify_once.add_argument("--baud", type=int, default=115200, help="Stream baud rate")
    verify_once.add_argument("--timeout", type=float, default=6.0, help="Timeout in seconds")

    verify_stream = sub.add_parser("verify-stream", help="Tail serial stream continuously")
    verify_stream.add_argument("--port", required=True, help="Serial port")
    verify_stream.add_argument("--baud", type=int, default=115200, help="Stream baud rate")

    return parser.parse_args()


def _load_manifest(path: str) -> dict[str, Any]:
    manifest_path = pathlib.Path(path).resolve()
    with manifest_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object")
    data["_manifest_dir"] = str(manifest_path.parent)
    return data


def _offset_key_to_int(offset: str) -> int:
    text = str(offset).strip().lower()
    if text.startswith("0x"):
        return int(text, 16)
    return int(text, 10)


def _build_esptool_args(manifest: dict[str, Any], port: str, baud: int) -> list[str]:
    extra = manifest.get("extra_esptool_args") or {}
    write_flash_args = manifest.get("write_flash_args") or []
    flash_files = manifest.get("flash_files") or {}
    manifest_dir = pathlib.Path(str(manifest["_manifest_dir"]))

    chip = str(extra.get("chip", "esp32s3"))
    before = str(extra.get("before", "default-reset"))
    after = str(extra.get("after", "hard-reset"))
    # Force ROM-loader mode to avoid packaged-data issues with esptool stub assets
    # in self-contained app bundles.
    use_stub = False

    if not isinstance(write_flash_args, list):
        raise ValueError("manifest.write_flash_args must be a list")
    if not isinstance(flash_files, dict) or not flash_files:
        raise ValueError("manifest.flash_files must be a non-empty object")

    args: list[str] = [
        "--chip",
        chip,
        "--port",
        port,
        "--baud",
        str(baud),
        "--before",
        before,
        "--after",
        after,
    ]
    if not use_stub:
        args.append("--no-stub")

    args.append("write-flash")
    args.extend(str(x) for x in write_flash_args)

    for offset, rel_path in sorted(flash_files.items(), key=lambda kv: _offset_key_to_int(kv[0])):
        bin_path = manifest_dir / str(rel_path)
        if not bin_path.exists():
            raise FileNotFoundError(f"missing firmware artifact: {bin_path}")
        args.append(str(offset))
        args.append(str(bin_path))

    return args


def _run_flash(port: str, manifest_path: str, baud: int) -> int:
    manifest = _load_manifest(manifest_path)
    args = _build_esptool_args(manifest, port=port, baud=baud)
    print(f"[info] Flashing {port} using {manifest_path}", flush=True)
    print(f"[info] esptool {' '.join(args)}", flush=True)

    try:
        esptool.main(args)
        return 0
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        return code
    except Exception as exc:  # pragma: no cover - runtime path
        print(f"[error] Flash failed: {exc}", file=sys.stderr, flush=True)
        return 1


def _run_verify_once(port: str, baud: int, timeout_s: float) -> int:
    deadline = time.time() + max(0.2, timeout_s)
    hits = 0
    try:
        ser = serial.Serial(port=port, baudrate=baud, timeout=0.5)
    except Exception as exc:  # pragma: no cover - runtime path
        print(f"[error] unable to open serial port: {exc}", file=sys.stderr, flush=True)
        return 1
    try:
        while time.time() < deadline:
            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                continue
            if msg.get("type") == "gesture" and isinstance(msg.get("name"), str):
                hits += 1
                if hits >= 1:
                    break
    finally:
        try:
            ser.close()
        except Exception:
            pass

    print(str(hits), flush=True)
    return 0 if hits >= 1 else 2


def _run_verify_stream(port: str, baud: int) -> int:
    try:
        ser = serial.Serial(port=port, baudrate=baud, timeout=0.5)
    except Exception as exc:  # pragma: no cover - runtime path
        print(f"[error] unable to open serial port: {exc}", file=sys.stderr, flush=True)
        return 1

    print("__VERIFY_READY__", flush=True)
    try:
        while True:
            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="ignore").strip()
            if line:
                print(line, flush=True)
    except KeyboardInterrupt:
        return 0
    finally:
        try:
            ser.close()
        except Exception:
            pass


def main() -> int:
    args = _parse_args()
    if args.command == "flash":
        return _run_flash(args.port, args.manifest, args.baud)
    if args.command == "verify-once":
        return _run_verify_once(args.port, args.baud, args.timeout)
    if args.command == "verify-stream":
        return _run_verify_stream(args.port, args.baud)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
