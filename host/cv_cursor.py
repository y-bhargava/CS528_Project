#!/usr/bin/env python3
"""MediaPipe-based hand cursor control for macOS."""

import argparse
import math
import signal
import sys
import time

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
        help="Normalized pinch threshold for click/drag (default: 0.045).",
    )
    parser.add_argument(
        "--drag-hold-ms",
        type=int,
        default=350,
        help="Pinch hold time in ms before drag starts (default: 350).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log cursor actions without moving/clicking the OS cursor.",
    )
    return parser


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _lerp(prev: float, nxt: float, alpha: float) -> float:
    return prev + alpha * (nxt - prev)


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def main() -> int:
    args = _build_arg_parser().parse_args()

    smooth = _clamp(args.smooth, 0.01, 1.0)
    pinch_threshold = max(0.005, args.pinch_threshold)
    drag_hold_seconds = max(0.05, args.drag_hold_ms / 1000.0)

    pyautogui.FAILSAFE = False
    screen_w, screen_h = pyautogui.size()
    cap = cv2.VideoCapture(args.camera_index)
    if not cap.isOpened():
        print(f"[error] unable to open camera index={args.camera_index}", file=sys.stderr)
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
    is_dragging = False
    was_pinching = False
    last_print = 0.0

    print(
        "[cv] ready - controls: move=index fingertip, pinch=click, pinch-hold=drag, q=quit",
        flush=True,
    )

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue

            frame = cv2.flip(frame, 1)
            h, w, _ = frame.shape
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = hands.process(rgb)

            if result.multi_hand_landmarks:
                hand = result.multi_hand_landmarks[0]
                lm = hand.landmark

                ix = lm[mp_hands.HandLandmark.INDEX_FINGER_TIP].x
                iy = lm[mp_hands.HandLandmark.INDEX_FINGER_TIP].y
                tx = _clamp(ix, 0.0, 1.0) * (screen_w - 1)
                ty = _clamp(iy, 0.0, 1.0) * (screen_h - 1)

                cursor_x = _lerp(cursor_x, tx, smooth)
                cursor_y = _lerp(cursor_y, ty, smooth)

                if args.dry_run:
                    now = time.monotonic()
                    if now - last_print > 0.2:
                        print(f"[cv] cursor x={int(cursor_x)} y={int(cursor_y)}", flush=True)
                        last_print = now
                else:
                    pyautogui.moveTo(cursor_x, cursor_y, _pause=False)

                thumb = (
                    lm[mp_hands.HandLandmark.THUMB_TIP].x,
                    lm[mp_hands.HandLandmark.THUMB_TIP].y,
                )
                index = (
                    lm[mp_hands.HandLandmark.INDEX_FINGER_TIP].x,
                    lm[mp_hands.HandLandmark.INDEX_FINGER_TIP].y,
                )
                pinch_dist = _distance(thumb, index)
                is_pinching = pinch_dist < pinch_threshold

                now = time.monotonic()
                if is_pinching and not was_pinching:
                    pinch_started_at = now
                if is_pinching and pinch_started_at is not None:
                    held = now - pinch_started_at
                    if held >= drag_hold_seconds and not is_dragging:
                        if args.dry_run:
                            print("[cv] dragDown", flush=True)
                        else:
                            pyautogui.mouseDown()
                        is_dragging = True

                if not is_pinching and was_pinching:
                    held = 0.0
                    if pinch_started_at is not None:
                        held = now - pinch_started_at
                    if is_dragging:
                        if args.dry_run:
                            print("[cv] dragUp", flush=True)
                        else:
                            pyautogui.mouseUp()
                        is_dragging = False
                    elif held < drag_hold_seconds:
                        if args.dry_run:
                            print("[cv] click", flush=True)
                        else:
                            pyautogui.click()
                    pinch_started_at = None

                was_pinching = is_pinching

                mp_draw.draw_landmarks(frame, hand, mp_hands.HAND_CONNECTIONS)
            else:
                if was_pinching and is_dragging:
                    if args.dry_run:
                        print("[cv] lost hand -> dragUp", flush=True)
                    else:
                        pyautogui.mouseUp()
                    is_dragging = False
                was_pinching = False
                pinch_started_at = None

            cv2.imshow("HCI Cursor (q to quit)", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
    except KeyboardInterrupt:
        pass
    finally:
        if is_dragging and not args.dry_run:
            pyautogui.mouseUp()
        cap.release()
        hands.close()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    raise SystemExit(main())
