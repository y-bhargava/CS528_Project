# Touchless HCI Project (CS528)

## What This App Is

This project is a touchless Human-Computer Interface (HCI) system. A wearable device
(ESP32 + IMU, and later ML/CV pipelines) detects motion/gestures and sends events to
the host app, which maps them to semantic actions and executes macOS controls.

## Goal

The immediate goal is a modular end-to-end pipeline that lets teams work independently:

- `esp/` team sends gesture events over the protocol.
- `ml/` team improves gesture recognition and event quality.
- `host/` team parses events, routes actions, and executes OS behavior safely.

This repo is structured so each layer can evolve without blocking the others, as long as
the shared event contract in `docs/protocol.md` stays aligned.

## Repo Layout

```text
host/   Python host listener/router/executor
esp/    ESP32 firmware (placeholder folder)
ml/     ML pipeline/training (placeholder folder)
docs/   Shared docs and protocol
```

## UV Setup

From repo root:

```bash
uv venv .venv
source .venv/bin/activate
uv pip install pyautogui
uv pip install opencv-python mediapipe
```

If `uv` is not installed yet on macOS:

```bash
brew install uv
```

## Run Host

Dry-run (default, no macOS side effects):

```bash
uv run python host/simulator.py | uv run python -u host/main.py
```

Live mode (real macOS actions):

```bash
uv run python host/main.py --input-file /tmp/hci_replay.ndjson --live
```

Curated live demo replay file (included in repo):

```bash
while IFS= read -r line; do
  sleep 5
  printf '%s\n' "$line"
done < docs/replay_live_demo.ndjson | uv run python host/main.py --live
```

Live mode prints:

- `[live] LIVE MODE ENABLED: real macOS actions may be executed`
- `[live] starting in 3...`
- `[live] starting in 2...`
- `[live] starting in 1...`
- `[live] live execution active`

## Live Action Backends

- `PREV_TAB` / `NEXT_TAB` / `NEW_TAB`: PyAutoGUI hotkeys
- `PLAY_PAUSE`: AppleScript via `osascript` (System Events key code `100`)

## Baseline Status

- Live tab controls are validated (`PREV_TAB`, `NEXT_TAB`, `NEW_TAB`).
- `PLAY_PAUSE` is wired and may fail if media control is unavailable or macOS automation permissions are not granted.
- Live mode is intentionally gated behind `--live` with a startup warning + countdown.

## Cooldown

Live execution uses per-action cooldowns in:

- `host/executor.py` (`LIVE_ACTION_COOLDOWNS`)

Cooldown skips are concise:

- `skip action=NEXT_TAB reason=cooldown remaining=0.18`

## CV Cursor (MediaPipe)

Run webcam-based cursor control (host-side):

```bash
uv run python host/cv_cursor.py
```

Safe dry-run (no real cursor movement/clicks):

```bash
uv run python host/cv_cursor.py --dry-run
```

Controls:

- Move index fingertip to move cursor
- Quick pinch (thumb + middle) to click
- Pinch and hold (thumb + middle) to drag
- Hold pinky-up pose (other fingers down) briefly to toggle routing mode (`CONTEXT`/`GLOBAL`)
- Press `q` to quit

## Unified Host Runner Modes

The host supports 3 modes in one entrypoint:

- `--mode esp`: ESP/NDJSON listener only (default)
- `--mode cv`: CV cursor controller only
- `--mode hybrid`: ESP + CV together (threaded single-process)

Context-aware ESP routing profiles:

- `Google Chrome`: left/right/up/down -> prev tab/next tab/new tab/close tab
- `Keynote` or `Microsoft PowerPoint`: left/right/up/down -> prev slide/next slide/start/exit presentation
- `Spotify`: left/right/up/down -> prev track/next track/volume up/volume down
- fallback/global desktop: left/right/up/down -> switch space left/right, mission control, show desktop

Touchless global switch:

- CV pinky-up hold toggles routing mode between `CONTEXT` and `GLOBAL`
- In `GLOBAL` mode, ESP gestures always use desktop mappings for app/window switching

Examples:

```bash
# ESP only
uv run python host/main.py --mode esp --serial-port /dev/cu.usbserial-10 --serial-baud 115200 --live

# CV only (dry-run by default; add --live for real cursor actions)
uv run python host/main.py --mode cv --camera-index 1 --live

# Hybrid (ESP + CV together)
uv run python host/main.py --mode hybrid --serial-port /dev/cu.usbserial-10 --camera-index 1 --live
```
