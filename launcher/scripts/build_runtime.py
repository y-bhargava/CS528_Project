#!/usr/bin/env python3
"""Build self-contained host + ESP tools for the Electron launcher.

Outputs:
  launcher/resources/runtime/touchless-host(.exe)
  launcher/resources/runtime/touchless-esp-tool(.exe)
"""

from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
HOST_ENTRY = ROOT / "host" / "main.py"
ESP_TOOL_ENTRY = ROOT / "launcher" / "runtime_src" / "esp_tool.py"
RUNTIME_OUT_DIR = ROOT / "launcher" / "resources" / "runtime"
BUILD_TMP = ROOT / "launcher" / ".build-runtime"


def _exe_name(base: str) -> str:
    return f"{base}.exe" if sys.platform.startswith("win") else base


def _remove_if_exists(target: pathlib.Path) -> None:
    if not target.exists():
        return
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()


def _run(cmd: list[str], cwd: pathlib.Path) -> None:
    print("[cmd]", " ".join(cmd), flush=True)
    local_cache_root = BUILD_TMP / "_cache"
    pyinstaller_config = local_cache_root / "pyinstaller"
    matplotlib_config = local_cache_root / "matplotlib"
    local_cache_root.mkdir(parents=True, exist_ok=True)
    pyinstaller_config.mkdir(parents=True, exist_ok=True)
    matplotlib_config.mkdir(parents=True, exist_ok=True)

    env = {**os.environ}
    env["PYINSTALLER_CONFIG_DIR"] = str(pyinstaller_config)
    env["MPLCONFIGDIR"] = str(matplotlib_config)

    proc = subprocess.run(cmd, cwd=str(cwd), env=env, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}")


def _pyinstaller(
    python: str,
    name: str,
    entry: pathlib.Path,
    work_root: pathlib.Path,
    extra_args: list[str],
) -> pathlib.Path:
    dist_dir = work_root / "dist"
    spec_dir = work_root / "spec"
    work_dir = work_root / "work"
    for folder in (dist_dir, spec_dir, work_dir):
        folder.mkdir(parents=True, exist_ok=True)

    cmd = [
        python,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        name,
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(spec_dir),
        *extra_args,
        str(entry),
    ]
    _run(cmd, cwd=ROOT)

    bundle_dir = dist_dir / name
    artifact = bundle_dir / _exe_name(name)
    if not artifact.exists():
        raise FileNotFoundError(f"expected artifact not found: {artifact}")
    return bundle_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Build bundled launcher runtime binaries")
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python interpreter used to run PyInstaller (default: current interpreter)",
    )
    args = parser.parse_args()

    if not HOST_ENTRY.exists():
        print(f"[error] missing host entry: {HOST_ENTRY}", file=sys.stderr)
        return 2
    if not ESP_TOOL_ENTRY.exists():
        print(f"[error] missing ESP tool entry: {ESP_TOOL_ENTRY}", file=sys.stderr)
        return 2

    if BUILD_TMP.exists():
        shutil.rmtree(BUILD_TMP)
    BUILD_TMP.mkdir(parents=True, exist_ok=True)

    # Build host runtime binary.
    host_bundle_dir = _pyinstaller(
        python=args.python,
        name="touchless-host",
        entry=HOST_ENTRY,
        work_root=BUILD_TMP / "host",
        extra_args=[
            "--paths",
            str(ROOT / "host"),
            "--hidden-import",
            "cv2",
            "--hidden-import",
            "mediapipe",
            "--hidden-import",
            "matplotlib",
            "--hidden-import",
            "pyautogui",
            "--hidden-import",
            "serial",
            "--collect-data",
            "mediapipe",
            "--exclude-module",
            "scipy",
            "--exclude-module",
            "mediapipe.tasks.python.test",
        ],
    )

    # Build ESP flashing + verify helper binary.
    esp_bundle_dir = _pyinstaller(
        python=args.python,
        name="touchless-esp-tool",
        entry=ESP_TOOL_ENTRY,
        work_root=BUILD_TMP / "esp_tool",
        extra_args=[
            "--hidden-import",
            "esptool",
            "--hidden-import",
            "serial",
            "--collect-data",
            "esptool",
        ],
    )

    RUNTIME_OUT_DIR.mkdir(parents=True, exist_ok=True)
    target_host_dir = RUNTIME_OUT_DIR / "touchless-host"
    target_esp_dir = RUNTIME_OUT_DIR / "touchless-esp-tool"
    legacy_helper_dir = ROOT / "launcher" / "resources" / "host-helper"
    legacy_host_file = RUNTIME_OUT_DIR / _exe_name("touchless-host")
    legacy_esp_file = RUNTIME_OUT_DIR / _exe_name("touchless-esp-tool")
    _remove_if_exists(legacy_host_file)
    _remove_if_exists(legacy_esp_file)
    _remove_if_exists(target_host_dir)
    _remove_if_exists(target_esp_dir)
    _remove_if_exists(legacy_helper_dir)
    shutil.copytree(host_bundle_dir, target_host_dir)
    shutil.copytree(esp_bundle_dir, target_esp_dir)

    print(f"[ok] host runtime: {target_host_dir / _exe_name('touchless-host')}")
    print(f"[ok] esp utility: {target_esp_dir / _exe_name('touchless-esp-tool')}")
    print("[next] run launcher/scripts/sync_firmware.py to refresh firmware bundle.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
