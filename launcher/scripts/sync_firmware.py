#!/usr/bin/env python3
"""Copy ESP build artifacts into launcher resources for offline flashing."""

from __future__ import annotations

import json
import pathlib
import shutil
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
ESP_BUILD = ROOT / "esp" / "build"
OUT_DIR = ROOT / "launcher" / "resources" / "firmware"
MANIFEST_NAME = "flasher_args.json"


def main() -> int:
    manifest_src = ESP_BUILD / MANIFEST_NAME
    if not manifest_src.exists():
        print(f"[error] missing manifest: {manifest_src}", file=sys.stderr)
        print("[hint] build firmware first from esp/ (idf.py build).", file=sys.stderr)
        return 2

    with manifest_src.open("r", encoding="utf-8") as fh:
        manifest = json.load(fh)

    flash_files = manifest.get("flash_files")
    if not isinstance(flash_files, dict) or not flash_files:
        print("[error] manifest flash_files is empty or invalid", file=sys.stderr)
        return 2

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    copied = []
    for _offset, rel in flash_files.items():
        rel_path = pathlib.Path(str(rel))
        src = ESP_BUILD / rel_path
        if not src.exists():
            print(f"[error] missing firmware binary: {src}", file=sys.stderr)
            return 2
        dst = OUT_DIR / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(dst)

    # Keep the exact manifest format produced by ESP-IDF so flash args stay aligned
    # with the built image.
    manifest_out = OUT_DIR / MANIFEST_NAME
    with manifest_out.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=4)
        fh.write("\n")

    print(f"[ok] wrote firmware bundle: {OUT_DIR}")
    print(f"[ok] manifest: {manifest_out}")
    for item in copied:
        print(f"[ok] file: {item.relative_to(OUT_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
