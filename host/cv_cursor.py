#!/usr/bin/env python3
"""MediaPipe-based hand cursor control for macOS."""

import argparse
import math
import signal
import sys
import threading
import time
from dataclasses import dataclass

import cv2  # type: ignore
import mediapipe as mp  # type: ignore
import pyautogui


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MediaPipe hand cursor controller")
    parser.add_argument(
        "--camera-index",
        type=int,
        default=0,
        help="OpenCV camera index (default: 0).",
    )
    parser.add_argument(
        "--smooth",
        type=float,
        default=0.22,
        help="Cursor smoothing factor in [0,1] (default: 0.22).",
    )
    parser.add_argument(
        "--pinch-threshold",
        type=float,
        default=0.045,
        help="Normalized pinch threshold for pinch gestures (default: 0.045).",
    )
    parser.add_argument(
        "--drag-hold-ms",
        type=int,
        default=350,
        help="Pinch hold time in ms before drag starts (default: 350).",
    )
    parser.add_argument(
        "--click-move-threshold",
        type=float,
        default=24.0,
        help="Max pointer drift in pixels allowed for click-on-release (default: 24).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log cursor actions without moving/clicking the OS cursor.",
    )
    return parser


@dataclass(frozen=True)
class CVCursorConfig:
    camera_index: int = 0
    smooth: float = 0.22
    pinch_threshold: float = 0.045
    drag_hold_ms: int = 350
    click_move_threshold: float = 24.0
    dry_run: bool = False
    show_window: bool = True
    window_title: str = "HCI Cursor (q to quit)"


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _lerp(prev: float, nxt: float, alpha: float) -> float:
    return prev + alpha * (nxt - prev)


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def run_cv_cursor(
    config: CVCursorConfig,
    stop_event: threading.Event | None = None,
) -> int:
    smooth = _clamp(config.smooth, 0.01, 1.0)
    pinch_threshold = max(0.005, config.pinch_threshold)
    drag_hold_seconds = max(0.05, config.drag_hold_ms / 1000.0)
    click_move_threshold = max(2.0, float(config.click_move_threshold))
    # Start drag if pinch movement exceeds this, even before hold timeout.
    drag_start_move_threshold = click_move_threshold * 1.6

    pyautogui.FAILSAFE = False
    screen_w, screen_h = pyautogui.size()
    cap = cv2.VideoCapture(config.camera_index)
    if not cap.isOpened():
        print(f"[error] unable to open camera index={config.camera_index}", file=sys.stderr)
        return 2

    mp_hands = mp.solutions.hands
    hands = mp_hands.Hands(
        model_complexity=0,
        max_num_hands=1,
        min_detection_confidence=0.55,
        min_tracking_confidence=0.55,
    )
    mp_draw = mp.solutions.drawing_utils

    cursor_x = screen_w / 2.0
    cursor_y = screen_h / 2.0
    pinch_started_at: float | None = None
    pinch_anchor_x: float | None = None
    pinch_anchor_y: float | None = None
    pinch_travel = 0.0
    is_dragging = False
    was_pinching = False
    last_print = 0.0

    print(
        "[cv] ready - controls: move=index fingertip, left=thumb+middle (click/drag), q=quit",
        flush=True,
    )

    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                break

            ok, frame = cap.read()
            if not ok:
                continue

            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = hands.process(rgb)
            ui_state = "NO_HAND"

            if result.multi_hand_landmarks:
                hand = result.multi_hand_landmarks[0]
                lm = hand.landmark

                ix = lm[mp_hands.HandLandmark.INDEX_FINGER_TIP].x
                iy = lm[mp_hands.HandLandmark.INDEX_FINGER_TIP].y
                tx = _clamp(ix, 0.0, 1.0) * (screen_w - 1)
                ty = _clamp(iy, 0.0, 1.0) * (screen_h - 1)

                thumb = (
                    lm[mp_hands.HandLandmark.THUMB_TIP].x,
                    lm[mp_hands.HandLandmark.THUMB_TIP].y,
                )
                middle = (
                    lm[mp_hands.HandLandmark.MIDDLE_FINGER_TIP].x,
                    lm[mp_hands.HandLandmark.MIDDLE_FINGER_TIP].y,
                )
                left_pinch_dist = _distance(thumb, middle)
                is_pinching = left_pinch_dist < pinch_threshold

                now = time.monotonic()
                if is_pinching and not was_pinching:
                    pinch_started_at = now
                    pinch_anchor_x = cursor_x
                    pinch_anchor_y = cursor_y
                    pinch_travel = 0.0
                if is_pinching and pinch_started_at is not None:
                    held = now - pinch_started_at
                    if pinch_anchor_x is not None and pinch_anchor_y is not None:
                        pinch_travel = _distance((tx, ty), (pinch_anchor_x, pinch_anchor_y))
                    if (held >= drag_hold_seconds or pinch_travel >= drag_start_move_threshold) and not is_dragging:
                        if config.dry_run:
                            print("[cv] dragDown", flush=True)
                        else:
                            pyautogui.mouseDown()
                        is_dragging = True

                # Keep cursor moving during pinch so drag destination remains visible.
                cursor_x = _lerp(cursor_x, tx, smooth)
                cursor_y = _lerp(cursor_y, ty, smooth)

                if config.dry_run:
                    if now - last_print > 0.2:
                        print(f"[cv] cursor x={int(cursor_x)} y={int(cursor_y)}", flush=True)
                        last_print = now
                else:
                    pyautogui.moveTo(cursor_x, cursor_y, _pause=False)

                if not is_pinching and was_pinching:
                    held = 0.0
                    if pinch_started_at is not None:
                        held = now - pinch_started_at
                    if is_dragging:
                        if config.dry_run:
                            print("[cv] dragUp", flush=True)
                        else:
                            pyautogui.mouseUp()
                        is_dragging = False
                    elif held < drag_hold_seconds and pinch_travel <= click_move_threshold:
                        if config.dry_run:
                            print("[cv] click", flush=True)
                        else:
                            pyautogui.click()
                    elif held < drag_hold_seconds and config.dry_run:
                        print("[cv] click canceled (movement)", flush=True)
                    pinch_started_at = None
                    pinch_anchor_x = None
                    pinch_anchor_y = None
                    pinch_travel = 0.0

                was_pinching = is_pinching

                if is_dragging:
                    ui_state = "DRAGGING"
                elif is_pinching:
                    ui_state = "CLICK_ARMED"
                else:
                    ui_state = "MOVE"
                mp_draw.draw_landmarks(frame, hand, mp_hands.HAND_CONNECTIONS)
            else:
                if was_pinching and is_dragging:
                    if config.dry_run:
                        print("[cv] lost hand -> dragUp", flush=True)
                    else:
                        pyautogui.mouseUp()
                    is_dragging = False
                was_pinching = False
                pinch_started_at = None
                pinch_anchor_x = None
                pinch_anchor_y = None
                pinch_travel = 0.0

            state_color = {
                "MOVE": (80, 220, 80),
                "CLICK_ARMED": (80, 200, 255),
                "DRAGGING": (60, 60, 255),
                "NO_HAND": (180, 180, 180),
            }.get(ui_state, (255, 255, 255))
            cv2.putText(
                frame,
                f"STATE: {ui_state}",
                (16, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                state_color,
                2,
                cv2.LINE_AA,
            )

            if config.show_window:
                cv2.imshow(config.window_title, frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        if is_dragging and not config.dry_run:
            pyautogui.mouseUp()
        cap.release()
        hands.close()
        if config.show_window:
            cv2.destroyAllWindows()

    return 0


def main() -> int:
    args = _build_arg_parser().parse_args()
    config = CVCursorConfig(
        camera_index=args.camera_index,
        smooth=args.smooth,
        pinch_threshold=args.pinch_threshold,
        drag_hold_ms=args.drag_hold_ms,
        click_move_threshold=args.click_move_threshold,
        dry_run=args.dry_run,
    )
    return run_cv_cursor(config)


if __name__ == "__main__":
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    raise SystemExit(main())
