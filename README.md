# Touchless HCI Project (CS528)

Touchless control system using:
- ESP32-S3 + MPU6050 gesture input
- CV hand tracking cursor control (MediaPipe)
- Context-aware host routing
- Electron launcher with onboarding, flashing, and runtime controls

## Gesture Mapping (Read This First)

The system uses **5 ESP gesture labels**:
- `left`
- `right`
- `up`
- `down`
- `twist`

`twist` is global pause/resume (unless disabled with `--disable-pause-toggle`).

### ESP Context Profiles

Routing is based on frontmost app (or forced desktop/global mode).

| Profile | App(s) | `left` | `right` | `up` | `down` |
|---|---|---|---|---|---|
| `chrome` | Google Chrome, Brave Browser | `PREV_TAB` | `NEXT_TAB` | `NEW_TAB` | `CLOSE_TAB` |
| `presentation` | Keynote, Microsoft PowerPoint | `PREV_SLIDE` | `NEXT_SLIDE` | `START_PRESENTATION` | `EXIT_PRESENTATION` |
| `spotify` | Spotify | `PREV_TRACK` | `NEXT_TRACK` | `VOLUME_UP` | `VOLUME_DOWN` |
| `desktop` | fallback/global desktop | `SWITCH_SPACE_LEFT` | `SWITCH_SPACE_RIGHT` | `MISSION_CONTROL` (or `PRESS_ENTER` with `--desktop-up-enter`) | `TRIGGER_SEARCH` |

### CV Gesture Controls (Right Hand Only)

CV currently tracks **right hand only**:
- Index fingertip: cursor movement
- Thumb + middle pinch (short): click
- Thumb + middle pinch hold: drag (desktop/global behavior)
- Thumb + middle pinch + vertical movement: scroll (when mapped app + context mode)
- Pinky-up hold (others down): clutch into `global`; release returns to `context`
- Thumbs-up hold: dictation hold (`Fn`) when `--enable-dictation-hold` is enabled

## Hotkey Prerequisites (Voice + Search)

Before running live demos, configure these two OS-level shortcuts:

### 1) Dictation Hold (`Fn`)

Dictation gesture uses a press-and-hold `Fn` key event.

You need a dictation/transcription app that listens to held `Fn`, for example:
- Handy: [https://handy.computer/download](https://handy.computer/download)

If no app is bound to held `Fn`, thumbs-up dictation gesture will trigger key hold but no transcription UI.

### 2) Search Trigger (`TRIGGER_SEARCH`)

Desktop/global `down` maps to `TRIGGER_SEARCH`, currently implemented as:
- macOS: `Cmd + Option + Space`

Make sure this combo is bound to your launcher/search tool:
- Spotlight (if remapped), or
- Raycast / Alfred / other app launcher

If your system uses a different combo, update your OS/app shortcut or change the host action mapping.

## Quick Start (Launcher / DMG)

### 1) Install

1. Download latest `Touchless Launcher-*.dmg` from project release assets.
2. Open the DMG.
3. Drag `Touchless Launcher` to `Applications`.
4. Launch from `Applications` (not from DMG volume).

### 2) Permissions

In launcher settings:
- Grant **Camera** (for CV/hybrid)
- Grant **Accessibility** (required for live OS action injection)

### 3) Quick Setup Flow

Use `Quick Setup`:
1. System Check
2. Connect ESP (serial port)
3. Flash Firmware
4. Verify Stream
5. Continue

If you do not have hardware connected, you can still test with replay input (see below).

## ESP Wiring (ESP32-S3 DevKitC + MPU6050)

- `SDA -> GPIO8`
- `SCL -> GPIO9`
- `VCC -> 3V3`
- `GND -> GND`

## Most Common Commands (CLI)

From repo root:

```bash
cd /Users/rayan/Documents/GitHub/CS528_Project
source .venv/bin/activate
```

### 1) Hybrid live (ESP + CV), headless CV, desktop up -> Enter

```bash
python3 -u host/main.py \
  --mode hybrid \
  --serial-port /dev/cu.usbserial-10 \
  --serial-baud 115200 \
  --camera-index 1 \
  --headless-cv \
  --hide-landmarks \
  --desktop-up-enter \
  --live
```

### 2) CV-only live, headless, dictation hold enabled

```bash
python3 -u host/main.py \
  --mode cv \
  --camera-index 1 \
  --headless-cv \
  --hide-landmarks \
  --enable-dictation-hold \
  --dictation-hold-ms 550 \
  --live
```

### 3) ESP-only live, desktop up -> Enter

```bash
python3 -u host/main.py \
  --mode esp \
  --serial-port /dev/cu.usbserial-10 \
  --serial-baud 115200 \
  --desktop-up-enter \
  --live
```

## Replay Testing (No ESP Hardware)

Use replay input to test routing + execution end-to-end:

```bash
python3 -u host/main.py \
  --mode hybrid \
  --input-file /tmp/hci_test.ndjson \
  --camera-index 1 \
  --headless-cv \
  --desktop-up-enter \
  --live
```

Bundled sample replay:
- `docs/replay_live_demo.ndjson`

## Full Flag Reference (`host/main.py`)

### Mode and Execution

- `--mode {esp,cv,hybrid}`: select input mode (default: `esp`)
- `--live`: enable real OS actions
- `--dry-run`: force dry-run (no OS actions)
- `--platform {auto,mac,windows}`: backend selection (default: `auto`)

### ESP Input

- `--serial-port PATH`: read NDJSON from serial device
- `--serial-baud N`: serial baud rate (default: `115200`)
- `--input-file PATH`: replay NDJSON file instead of serial/stdin

### CV Input

- `--camera-index N`: OpenCV camera index (default: `0`)
- `--smooth X`: cursor smoothing factor in `[0,1]` (default: `0.22`)
- `--pinch-threshold X`: pinch detection threshold (default: `0.045`)
- `--drag-hold-ms N`: pinch hold before drag start (default: `350`)
- `--click-move-threshold X`: max drift for click-on-release (default: `24.0`)
- `--hide-landmarks`: disable overlay landmarks/text drawing
- `--headless-cv`: run CV without preview window
- `--enable-dictation-hold`: enable thumbs-up hold -> `Fn` key hold
- `--dictation-hold-ms N`: dictation hold trigger time (default: `550`)

### Routing and Behavior

- `--disable-context-routing`: force desktop/global mapping always
- `--desktop-up-enter`: map desktop `up` to `PRESS_ENTER` instead of `MISSION_CONTROL`
- `--disable-pause-toggle`: ignore `twist` pause/resume gesture

### Accessibility Diagnostics (macOS)

- `--check-accessibility`: print runtime trust and exit
- `--prompt-accessibility`: request trust prompt and exit
- `--allow-untrusted-accessibility`: do not hard-fail when trust probe reports untrusted

## Launcher Features

Launcher (`launcher/`) provides:
- mode presets (`esp`, `cv`, `hybrid`)
- live/dry run controls
- serial port detection
- firmware flash + stream verify
- permission status and deep links
- log view and quick setup flow

## Build / Package Launcher

From repository root:

```bash
python3 -m pip install -r launcher/runtime_src/requirements-build.txt
bash launcher/scripts/prepare_release.sh
cd launcher
npm install
npm run build:dmg
```

Output DMG:
- `launcher/dist/Touchless Launcher-0.1.0-arm64.dmg`

## Troubleshooting

- Serial port missing: reconnect board/cable, refresh ports, close other serial monitors.
- Camera works in terminal but not launcher: confirm permission granted to **Touchless Launcher**.
- CV not moving cursor: verify right hand is visible and `camera-index` is correct.
- First run is slow: font/cache warmup can happen once and then improve.
- Flash fails without hardware: expected; you can still verify pipeline wiring with replay mode.

## Repository Layout

```text
host/      host runtime, routing, CV cursor control
esp/       ESP-IDF firmware
ml/        model collection/training/export scripts
docs/      protocol + replay files
launcher/  Electron app, onboarding, packaging scripts
```
