# Touchless HCI Launcher

Electron desktop launcher for the touchless host runtime with bundled offline flashing.

## What It Provides

- Unified mode selector: `esp`, `cv`, `hybrid`
- Safe launch controls: dry-run/live, start/stop process buttons
- Platform backend selector: `auto`, `mac`, `windows`
- Config persistence between runs
- Permission checks + deep links to OS settings
- Onboarding flow:
  - serial port detection
  - ESP firmware flashing
  - live stream verification

## Self-Contained Packaging Model

Release builds can run without local ESP-IDF and without a Python/venv install on the target machine.

- Bundled host runtime executable: `touchless-host`
- Bundled ESP utility executable: `touchless-esp-tool`
- Bundled firmware artifacts:
  - `bootloader.bin`
  - `partition-table.bin`
  - `gesture_controller.bin`
  - `flasher_args.json`

At runtime, launcher resolves resources from:

- Development: `launcher/resources/...`
- Packaged app: `process.resourcesPath/...`

## Build Release Resources

Run from repository root:

```bash
python3 -m pip install -r launcher/runtime_src/requirements-build.txt
python3 launcher/scripts/build_runtime.py --python /path/to/python
python3 launcher/scripts/sync_firmware.py
```

Or use the convenience wrapper:

```bash
bash launcher/scripts/prepare_release.sh
```

## Build Electron App

From `launcher/`:

```bash
npm run build:dmg
```

This command prepares resources and builds a macOS DMG.

## Notes

- If bundled runtime binaries are not present in development, launcher falls back to workspace Python (`.venv` if available).
- In packaged app mode, launcher requires bundled runtime artifacts and will not fall back to `idf.py`/workspace scripts.
- Firmware bundle is generated from `esp/build/flasher_args.json` so flash offsets/settings stay aligned with the latest ESP build output.
- On macOS, if camera permission is already `denied`, the OS will not show the camera prompt again; users must enable it in System Settings and restart the app.
- Onboarding treats camera/accessibility as recommended for CV/Hybrid; ESP flash + verify can proceed without camera permission.
