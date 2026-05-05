#!/usr/bin/env python3
"""MediaPipe-based hand cursor control."""

import argparse
import math
import signal
import sys
import threading
import time
import warnings
from dataclasses import dataclass
from typing import Callable

import cv2  # type: ignore
import mediapipe as mp  # type: ignore
import pyautogui
from app_monitor import FrontmostAppMonitor
from platform_util import is_mac
from router import APP_ALIASES

warnings.filterwarnings(
    "ignore",
    message=r"SymbolDatabase\.GetPrototype\(\) is deprecated.*",
    category=UserWarning,
)


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
    parser.add_argument(
        "--hide-landmarks",
        action="store_true",
        help="Disable hand landmark overlay drawing for better performance.",
    )
    parser.add_argument(
        "--enable-dictation-hold",
        action="store_true",
        help="Enable thumbs-up hold to press-and-hold Fn for dictation apps.",
    )
    parser.add_argument(
        "--dictation-hold-ms",
        type=int,
        default=550,
        help="Thumbs-up hold time in ms before dictation key down (default: 550).",
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
    draw_landmarks: bool = True
    mode_state: object | None = None
    mode_toggle_hold_ms: int = 650
    mode_toggle_cooldown_ms: int = 1000
    scroll_step_pixels: float = 18.0
    on_mode_change: Callable[[str], None] | None = None
    app_poll_interval_seconds: float = 1.0
    enable_dictation_hold: bool = False
    dictation_hold_ms: int = 550


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _lerp(prev: float, nxt: float, alpha: float) -> float:
    return prev + alpha * (nxt - prev)


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _is_pinky_toggle_pose(
    hand_landmarks,
    mp_hands,
) -> bool:
    lm = hand_landmarks.landmark

    def _is_extended(tip_idx, pip_idx) -> bool:
        # In flipped selfie view, lower y is generally "up/extended".
        return lm[tip_idx].y < (lm[pip_idx].y - 0.03)

    pinky_up = _is_extended(
        mp_hands.HandLandmark.PINKY_TIP,
        mp_hands.HandLandmark.PINKY_PIP,
    )
    index_down = not _is_extended(
        mp_hands.HandLandmark.INDEX_FINGER_TIP,
        mp_hands.HandLandmark.INDEX_FINGER_PIP,
    )
    middle_down = not _is_extended(
        mp_hands.HandLandmark.MIDDLE_FINGER_TIP,
        mp_hands.HandLandmark.MIDDLE_FINGER_PIP,
    )
    ring_down = not _is_extended(
        mp_hands.HandLandmark.RING_FINGER_TIP,
        mp_hands.HandLandmark.RING_FINGER_PIP,
    )

    thumb_tip = (
        lm[mp_hands.HandLandmark.THUMB_TIP].x,
        lm[mp_hands.HandLandmark.THUMB_TIP].y,
    )
    middle_mcp = (
        lm[mp_hands.HandLandmark.MIDDLE_FINGER_MCP].x,
        lm[mp_hands.HandLandmark.MIDDLE_FINGER_MCP].y,
    )
    thumb_tucked = _distance(thumb_tip, middle_mcp) < 0.18

    return pinky_up and index_down and middle_down and ring_down and thumb_tucked


def _is_thumbs_up_pose(
    hand_landmarks,
    mp_hands,
) -> bool:
    lm = hand_landmarks.landmark

    def _is_extended(tip_idx, pip_idx) -> bool:
        return lm[tip_idx].y < (lm[pip_idx].y - 0.03)

    index_down = not _is_extended(
        mp_hands.HandLandmark.INDEX_FINGER_TIP,
        mp_hands.HandLandmark.INDEX_FINGER_PIP,
    )
    middle_down = not _is_extended(
        mp_hands.HandLandmark.MIDDLE_FINGER_TIP,
        mp_hands.HandLandmark.MIDDLE_FINGER_PIP,
    )
    ring_down = not _is_extended(
        mp_hands.HandLandmark.RING_FINGER_TIP,
        mp_hands.HandLandmark.RING_FINGER_PIP,
    )
    pinky_down = not _is_extended(
        mp_hands.HandLandmark.PINKY_TIP,
        mp_hands.HandLandmark.PINKY_PIP,
    )

    thumb_tip = lm[mp_hands.HandLandmark.THUMB_TIP]
    thumb_ip = lm[mp_hands.HandLandmark.THUMB_IP]
    thumb_mcp = lm[mp_hands.HandLandmark.THUMB_MCP]
    thumb_up = thumb_tip.y < (thumb_ip.y - 0.025) and thumb_ip.y < (thumb_mcp.y - 0.015)

    return thumb_up and index_down and middle_down and ring_down and pinky_down


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
    was_scrolling = False
    last_scroll_ty: float | None = None
    last_print = 0.0
    fist_started_at: float | None = None
    mode_hold_seconds = max(0.25, config.mode_toggle_hold_ms / 1000.0)
    scroll_step_pixels = max(4.0, float(config.scroll_step_pixels))
    active_app_name: str | None = None
    dictation_pose_started_at: float | None = None
    dictation_key_held = False
    dictation_hold_seconds = max(0.2, config.dictation_hold_ms / 1000.0)
    dictation_supported = is_mac()
    dictation_warned_unsupported = False
    app_monitor = FrontmostAppMonitor(
        poll_interval_seconds=config.app_poll_interval_seconds,
    )
    app_monitor.start()

    print(
        "[cv] ready - controls: move=index fingertip, left=thumb+middle (click/scroll or drag), mode toggle=pinky-up hold, q=quit",
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
            cv_drag_mode = True

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
                cached_app_name = app_monitor.get_latest()
                if cached_app_name is not None:
                    active_app_name = cached_app_name
                current_mode = "context"
                if config.mode_state is not None:
                    try:
                        current_mode = str(config.mode_state.get_mode())
                    except Exception:
                        current_mode = "context"
                app_is_mapped = False
                if active_app_name:
                    app_is_mapped = (
                        active_app_name in APP_ALIASES
                        or active_app_name.lower() in APP_ALIASES
                    )
                cv_drag_mode = current_mode == "global" or not app_is_mapped
                is_toggle_pose = _is_pinky_toggle_pose(hand, mp_hands)
                is_dictation_pose = _is_thumbs_up_pose(hand, mp_hands)
                if is_toggle_pose:
                    if fist_started_at is None:
                        fist_started_at = now
                    ready = now - fist_started_at >= mode_hold_seconds
                    if ready and config.mode_state is not None:
                        try:
                            current_mode = str(config.mode_state.get_mode())
                            if current_mode != "global":
                                new_mode = config.mode_state.set_mode("global")
                                if config.on_mode_change is not None:
                                    config.on_mode_change(new_mode)
                        except Exception:
                            pass
                else:
                    fist_started_at = None
                    if config.mode_state is not None:
                        try:
                            current_mode = str(config.mode_state.get_mode())
                            if current_mode != "context":
                                new_mode = config.mode_state.set_mode("context")
                                if config.on_mode_change is not None:
                                    config.on_mode_change(new_mode)
                        except Exception:
                            pass

                if config.enable_dictation_hold and not dictation_supported:
                    if not dictation_warned_unsupported:
                        print(
                            "[cv-warning] dictation hold is only supported on macOS",
                            flush=True,
                        )
                        dictation_warned_unsupported = True
                elif (
                    config.enable_dictation_hold
                    and dictation_supported
                    and is_dictation_pose
                ):
                    if dictation_pose_started_at is None:
                        dictation_pose_started_at = now
                    if (
                        not dictation_key_held
                        and (now - dictation_pose_started_at) >= dictation_hold_seconds
                    ):
                        if config.dry_run:
                            print("[cv] dictation keyDown fn", flush=True)
                        else:
                            pyautogui.keyDown("fn")
                        dictation_key_held = True
                else:
                    dictation_pose_started_at = None
                    if dictation_key_held:
                        if config.dry_run:
                            print("[cv] dictation keyUp fn", flush=True)
                        else:
                            pyautogui.keyUp("fn")
                        dictation_key_held = False

                if is_pinching and not was_pinching:
                    pinch_started_at = now
                    pinch_anchor_x = cursor_x
                    pinch_anchor_y = cursor_y
                    pinch_travel = 0.0
                if is_pinching and pinch_started_at is not None:
                    held = now - pinch_started_at
                    if pinch_anchor_x is not None and pinch_anchor_y is not None:
                        pinch_travel = _distance((tx, ty), (pinch_anchor_x, pinch_anchor_y))
                    if cv_drag_mode:
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

                is_scrolling = False
                if not cv_drag_mode and is_pinching:
                    if last_scroll_ty is None:
                        last_scroll_ty = ty
                    dy = last_scroll_ty - ty
                    steps = int(dy / scroll_step_pixels)
                    if steps != 0:
                        is_scrolling = True
                        if config.dry_run:
                            print(f"[cv] scroll steps={steps}", flush=True)
                        else:
                            pyautogui.scroll(steps)
                        # Preserve fractional remainder by resetting relative to consumed steps.
                        last_scroll_ty = ty + (dy - (steps * scroll_step_pixels))
                    else:
                        last_scroll_ty = ty
                else:
                    last_scroll_ty = None

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
                    elif held < drag_hold_seconds and pinch_travel <= click_move_threshold and not was_scrolling:
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
                was_scrolling = is_scrolling

                if is_dragging:
                    ui_state = "DRAGGING"
                elif is_scrolling:
                    ui_state = "SCROLLING"
                elif is_pinching:
                    ui_state = "CLICK_ARMED"
                elif config.enable_dictation_hold and is_dictation_pose:
                    ui_state = "DICTATION_ARMED"
                elif is_toggle_pose:
                    ui_state = "MODE_ARMED"
                else:
                    ui_state = "MOVE"
                if config.draw_landmarks:
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
                was_scrolling = False
                last_scroll_ty = None
                fist_started_at = None
                dictation_pose_started_at = None
                if dictation_key_held:
                    if config.dry_run:
                        print("[cv] dictation keyUp fn (lost hand)", flush=True)
                    else:
                        pyautogui.keyUp("fn")
                    dictation_key_held = False
                if config.mode_state is not None:
                    try:
                        current_mode = str(config.mode_state.get_mode())
                        if current_mode != "context":
                            new_mode = config.mode_state.set_mode("context")
                            if config.on_mode_change is not None:
                                config.on_mode_change(new_mode)
                    except Exception:
                        pass

            current_mode = "context"
            if config.mode_state is not None:
                try:
                    current_mode = str(config.mode_state.get_mode())
                except Exception:
                    current_mode = "context"

            if config.draw_landmarks:
                state_color = {
                    "MOVE": (80, 220, 80),
                    "CLICK_ARMED": (80, 200, 255),
                    "DRAGGING": (60, 60, 255),
                    "SCROLLING": (190, 130, 255),
                    "DICTATION_ARMED": (255, 120, 120),
                    "MODE_ARMED": (255, 180, 80),
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
                cv2.putText(
                    frame,
                    f"MODE: {current_mode.upper()}",
                    (16, 58),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (240, 240, 240),
                    2,
                    cv2.LINE_AA,
                )
                cv2.putText(
                    frame,
                    f"APP: {(active_app_name or 'Unknown')}",
                    (16, 84),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (220, 220, 220),
                    1,
                    cv2.LINE_AA,
                )
                cv2.putText(
                    frame,
                    f"CV_BEHAVIOR: {'DRAG' if cv_drag_mode else 'SCROLL'}",
                    (16, 106),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (220, 220, 220),
                    1,
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
        if dictation_key_held and not config.dry_run:
            pyautogui.keyUp("fn")
        if is_dragging and not config.dry_run:
            pyautogui.mouseUp()
        app_monitor.stop()
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
        draw_landmarks=not args.hide_landmarks,
        enable_dictation_hold=args.enable_dictation_hold,
        dictation_hold_ms=args.dictation_hold_ms,
    )
    return run_cv_cursor(config)


if __name__ == "__main__":
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    raise SystemExit(main())
