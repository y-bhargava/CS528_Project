import json
import pickle
import signal
import sys
import time
from collections import deque
from pathlib import Path

import numpy as np

try:
    from features import AXIS_COLS, WINDOW_SIZE, extract_features
except ImportError:
    from .features import AXIS_COLS, WINDOW_SIZE, extract_features

MODEL_PATH = Path(__file__).parent / "model_svm.pkl"

STRIDE = 25

CONFIDENCE_THRESHOLD = 0.75

GESTURE_COOLDOWN: dict[str, float] = {
    "left": 0.6,
    "right": 0.6,
    "up": 0.6,
    "down": 0.6,
}



def _parse_imu_line(line: str) -> list[float] | None:
    stripped = line.strip()
    if not stripped:
        return None
    try:
        msg = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if msg.get("type") != "imu":
        return None
    try:
        return [float(msg[ax]) for ax in AXIS_COLS]
    except (KeyError, ValueError, TypeError):
        return None

def _emit_gesture(name: str, confidence: float) -> None:
    msg = {
        "type": "gesture",
        "name": name,
        "confidence": round(confidence, 3),
        "source": "ml",
    }
    print(json.dumps(msg, separators=(",", ":")), flush=True)


def main() -> int:
    if not MODEL_PATH.exists():
        print(
            f"[classifier] model not found: {MODEL_PATH}\n"
            f"[classifier] Run 'python ml/train_svm.py' first.",
            file=sys.stderr,
        )
        return 1

    print("[classifier] Loading gesture model...", file=sys.stderr, flush=True)
    with open(MODEL_PATH, "rb") as fh:
        bundle = pickle.load(fh)
    pipeline = bundle["pipeline"]
    gesture_classes = bundle["gesture_classes"]
    model_type = bundle.get("model_type", "unknown")
    axes = bundle.get("axes", AXIS_COLS)
    if axes != AXIS_COLS:
        print(
            f"[classifier] model axes {axes} do not match runtime axes {AXIS_COLS}",
            file=sys.stderr,
        )
        return 1

    print(
        f"[classifier] Ready ({model_type}). Classes: {gesture_classes}. "
        f"Window={WINDOW_SIZE} Stride={STRIDE} Threshold={CONFIDENCE_THRESHOLD}",
        file=sys.stderr,
        flush=True,
    )

    buffer: deque[list[float]] = deque(maxlen=WINDOW_SIZE)
    samples_since_last_inference = 0
    last_gesture_time: dict[str, float] = {}

    for line in sys.stdin:
        row = _parse_imu_line(line)
        if row is None:
            continue

        buffer.append(row)
        samples_since_last_inference += 1

        if len(buffer) < WINDOW_SIZE or samples_since_last_inference < STRIDE:
            continue

        samples_since_last_inference = 0

        window = np.array(buffer, dtype=np.float32)
        features = extract_features(window).reshape(1, -1)
        expected = getattr(pipeline, "n_features_in_", features.shape[1])
        if features.shape[1] != expected:
            print(
                f"[classifier] feature mismatch: model expects {expected}, "
                f"runtime produced {features.shape[1]}",
                file=sys.stderr,
            )
            return 1

        probs = pipeline.predict_proba(features)[0]
        pred_idx = int(np.argmax(probs))
        confidence = float(probs[pred_idx])
        gesture = gesture_classes[pred_idx]

        if confidence < CONFIDENCE_THRESHOLD:
            print(
                f"[classifier] low confidence: {gesture}={confidence:.2f}",
                file=sys.stderr,
            )
            continue

        now = time.monotonic()
        cooldown = GESTURE_COOLDOWN.get(gesture, 0.6)
        last = last_gesture_time.get(gesture)
        if last is not None and (now - last) < cooldown:
            continue

        last_gesture_time[gesture] = now
        _emit_gesture(gesture, confidence)

    return 0


if __name__ == "__main__":
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except OSError:
            pass
        raise SystemExit(0)
    except KeyboardInterrupt:
        raise SystemExit(0)
