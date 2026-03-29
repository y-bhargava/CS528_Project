# Touchless HCI Protocol

## Overview
This protocol defines how the ESP32 (or simulator / ML pipeline) communicates with the host application.

The system is designed to be:
- serial-first and serial-only (USB)
- cross-platform (Mac-first executor, but generic core)
- extensible (cursor, ML, CV later)

---

# Transport

## Current (v1)
- Primary: Serial (USB)
- Messages are sent as newline-delimited JSON (NDJSON)

Example stream:
{"type":"gesture","name":"swipe_left","confidence":0.91}
{"type":"gesture","name":"swipe_right","confidence":0.88}

NOTE: Transport is fixed to serial for this protocol version.

---

# Message Types

## Supported in v1

### 1. Gesture
Represents a recognized gesture (rule-based or ML).

Example:
{
  "type": "gesture",
  "name": "swipe_left",
  "confidence": 0.91,
  "timestamp": 1712345678
}

Fields:
- name: gesture identifier
- confidence: optional (0–1)
- timestamp: optional

---

### 2. IMU
Raw sensor data from MPU6050.

Example:
{
  "type": "imu",
  "timestamp": 1712345678,
  "ax": 0.12,
  "ay": -0.84,
  "az": 0.42,
  "gx": 1.34,
  "gy": -0.18,
  "gz": 0.09
}

Used for:
- debugging
- logging
- ML training
- visualization

---

### 3. Status
Device/system state updates.

Example:
{
  "type": "status",
  "device": "esp32",
  "connected": true,
  "mode": "gesture_only"
}

Used for:
- connection state
- calibration state
- system mode

---

## Planned / Optional Message Types

### Cursor
Relative cursor movement (for IMU-based cursor control).

Example:
{
  "type": "cursor",
  "dx": 12,
  "dy": -4,
  "timestamp": 1712345678
}

---

### Action
Direct semantic command (bypasses gesture layer).

Example:
{
  "type": "action",
  "name": "NEXT_TAB"
}

---

### Click
Explicit mouse click event.

Example:
{
  "type": "click",
  "button": "left"
}

---

### Scroll
Scroll event.

Example:
{
  "type": "scroll",
  "dy": -3
}

---

### Mode
Switch between interaction modes.

Example:
{
  "type": "mode",
  "name": "gesture_only"
}

---

### Calibration
Calibration lifecycle events.

Example:
{
  "type": "calibration",
  "state": "complete"
}

---

### Error
Error reporting.

Example:
{
  "type": "error",
  "source": "imu",
  "message": "packet dropped"
}

---

### Heartbeat
Keepalive signal.

Example:
{
  "type": "heartbeat",
  "timestamp": 1712345678
}

---

# Gesture Set (v1)

We start with a small, high-separation gesture set.

## Supported Gestures

- swipe_left
  Strong leftward motion

- swipe_right
  Strong rightward motion

- flick_up
  Quick upward motion

- hold
  Hand remains relatively still for a short duration

---

# Semantic Actions

Gestures are mapped to abstract actions (not OS-specific).

## Core Actions

- PREV_TAB
- NEXT_TAB
- PLAY_PAUSE
- NEW_TAB

---

# Example Mappings

## Browser / Productivity Demo
- swipe_left → PREV_TAB
- swipe_right → NEXT_TAB
- flick_up → NEW_TAB
- hold → PLAY_PAUSE or open project page

---

## Media Control Demo
- swipe_left → PREV_TRACK
- swipe_right → NEXT_TRACK
- flick_up → VOLUME_UP
- hold → PLAY_PAUSE

---

## Presentation Demo
- swipe_left → PREV_SLIDE
- swipe_right → NEXT_SLIDE
- flick_up → START_PRESENTATION
- hold → PAUSE / BLACK SCREEN

---

# Notes

## Why only a few message types in v1?
To:
- reduce coordination overhead
- avoid breaking changes early
- keep ESP / ML / host aligned

## Why simple gestures?
IMU-based sensing works best with:
- large directional movements
- clear temporal signatures

Avoid:
- pinch
- finger pose gestures
- complex rotations (v1)

---

# Design Principles

- Serial-only transport (USB)
- Extensible message schema
- Separation of:
  - sensing (ESP / ML)
  - interpretation (gesture)
  - meaning (semantic action)
  - execution (host OS)

---

# Host Execution Baseline (Current)

- Host runs in dry-run by default; real OS actions require `--live`.
- Live startup safety logs:
  - `[live] LIVE MODE ENABLED: real macOS actions may be executed`
  - `[live] starting in 3...` / `2...` / `1...`
  - `[live] live execution active`
- Live backends:
  - `PREV_TAB`, `NEXT_TAB`, `NEW_TAB` use PyAutoGUI shortcuts
  - `PLAY_PAUSE` uses AppleScript (`osascript`) with System Events key code `100`
- Live cooldown is per-action and logs concise skips:
  - `skip action=NEXT_TAB reason=cooldown remaining=0.18`
- `PLAY_PAUSE` can fail at runtime if media control is unavailable or macOS automation permissions are missing.

---

# Future Extensions

- CV-based cursor input
- TinyML gesture classification
- Multi-gesture sequences
- User calibration profiles
- Custom gesture bindings
