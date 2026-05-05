# Touchless HCI Launcher

Electron desktop launcher for `host/main.py` with a configuration-first workflow.

## What It Provides

- Unified mode selector: `esp`, `cv`, `hybrid`
- Safe launch controls: dry-run/live, start/stop process buttons
- Platform backend selector: `auto`, `mac`, `windows`
- Config persistence between runs
- Live command preview so runtime flags are transparent
- Runtime logs from stdout/stderr in-app
- Permission check panel (camera/microphone/screen/accessibility)
- Deep links to OS settings for quick permission setup

## Notes

- The launcher spawns the existing Python host process. No host logic is reimplemented.
- Saved launcher config is stored in Electron user data (`hci-launcher-config.json`).
- For dictation hold workflows on macOS, pair with a push-to-talk app such as Handy.
