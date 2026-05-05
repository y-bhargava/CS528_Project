# Touchless HCI Project (CS528)

## What This App Is

This project is a touchless Human-Computer Interface (HCI) system. A wearable device
(ESP32 + IMU, and later ML/CV pipelines) detects motion/gestures and sends events to
the host app, which maps them to semantic actions and executes OS controls.

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
launcher/  Electron desktop launcher (config + permissions + run controls)
```

## Desktop Launcher (Electron)

A minimal desktop launcher is available in `launcher/` with:

- mode presets (`esp`, `cv`, `hybrid`)
- live/dry-run toggle
- platform backend selection (`auto`, `mac`, `windows`)
- serial/replay and CV tuning controls
- permission status panel + settings deep links
- start/stop process controls and live host logs
- saved local config between launches

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

## Launcher Setup

The Electron launcher lives in `launcher/` and controls host startup/config from a GUI.

```bash
cd launcher
npm install
npm start
```

## Run Host

Dry-run (default, no OS side effects):

```bash
uv run python host/simulator.py | uv run python -u host/main.py
```

Live mode (real OS actions):

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

- `[live] LIVE MODE ENABLED: real OS actions may be executed`
- `[live] starting in 3...`
- `[live] starting in 2...`
- `[live] starting in 1...`
- `[live] live execution active`

## Live Action Backends

- `PREV_TAB` / `NEXT_TAB` / `NEW_TAB`: PyAutoGUI hotkeys
- `PLAY_PAUSE`: AppleScript via `osascript` (System Events key code `100`)

## Baseline Status

- Live tab controls are validated (`PREV_TAB`, `NEXT_TAB`, `NEW_TAB`).
- `PLAY_PAUSE` is wired and may fail if media control is unavailable or automation permissions are not granted.
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
- Mapped app + context mode: pinch + vertical move to scroll
- Unmapped app or global clutch mode: pinch and hold to drag
- Hold pinky-up pose (other fingers down) briefly to clutch into `GLOBAL`; release to return to `CONTEXT`
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

- CV pinky-up hold acts as a clutch: hold for `GLOBAL`, release for `CONTEXT`
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

## Quick Start Commands

Use these as the default launch recipes.

### 0) Setup (once)

```bash
cd /Users/rayan/Documents/GitHub/CS528_Project
uv venv .venv
source .venv/bin/activate
uv pip install pyautogui opencv-python mediapipe
```

### 1) CV only (dry-run, safe default)

```bash
cd /Users/rayan/Documents/GitHub/CS528_Project
source .venv/bin/activate
python3 -u host/main.py --mode cv --camera-index 1 --hide-landmarks
```

### 2) CV only (live actions)

```bash
cd /Users/rayan/Documents/GitHub/CS528_Project
source .venv/bin/activate
python3 -u host/main.py --mode cv --camera-index 1 --live --hide-landmarks
```

### 3) CV only + dictation hold (Handy-style)

Prerequisite: install and configure a push-to-talk transcription app that uses held `Fn`
(for example Handy: https://handy.computer/download).

```bash
cd /Users/rayan/Documents/GitHub/CS528_Project
source .venv/bin/activate
python3 -u host/main.py --mode cv --camera-index 1 --live --hide-landmarks --enable-dictation-hold --dictation-hold-ms 550
```

### 4) Hybrid dry-run using replay gestures

```bash
cd /Users/rayan/Documents/GitHub/CS528_Project
source .venv/bin/activate

cat > /tmp/hci_test.ndjson <<'EOF'
{"type":"gesture","name":"left"}
{"type":"gesture","name":"right"}
{"type":"gesture","name":"up"}
{"type":"gesture","name":"down"}
EOF

while IFS= read -r line; do
  sleep 5
  printf '%s\n' "$line"
done < /tmp/hci_test.ndjson | python3 -u host/main.py --mode hybrid --input-file /dev/stdin --camera-index 1 --hide-landmarks
```

### 5) Hybrid live with real ESP serial

```bash
cd /Users/rayan/Documents/GitHub/CS528_Project
source .venv/bin/activate
python3 -u host/main.py --mode hybrid --serial-port /dev/cu.usbserial-10 --serial-baud 115200 --camera-index 1 --live --hide-landmarks
```

### 6) ESP only (dry-run routing test)

```bash
cd /Users/rayan/Documents/GitHub/CS528_Project
source .venv/bin/activate
python3 -u host/main.py --mode esp --serial-port /dev/cu.usbserial-10 --serial-baud 115200
```

## Flag Reference

Common flags for `host/main.py`:

- `--mode esp|cv|hybrid`: selects ESP-only, CV-only, or both together.
- `--platform auto|mac|windows`: selects platform backend (`auto` detects from OS).
- `--live`: enables real OS actions. Omit for dry-run logging only.
- `--dry-run`: explicitly forces dry-run mode (useful when scripting launch flags).
- `--camera-index N`: selects webcam index (your known-good value is often `1`).
- `--serial-port PATH`: serial device for ESP input (example: `/dev/cu.usbserial-10`).
- `--serial-baud N`: serial baud rate (default `115200`).
- `--input-file PATH`: replay NDJSON gestures from file/stdin (for testing without ESP).
- `--hide-landmarks`: hides hand landmarks and debug overlay text for cleaner/faster preview.
- `--disable-context-routing`: forces desktop/global profile instead of app-aware mapping.
- `--enable-dictation-hold`: enables thumbs-up hold -> hold `Fn` (for dictation tools like Handy).
- `--dictation-hold-ms N`: hold duration before dictation key-down (default `550` ms).
