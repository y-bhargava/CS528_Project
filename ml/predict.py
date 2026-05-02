"""
predict.py — test the trained SVM gesture model

OFFLINE  (test against a saved CSV file):
    python predict.py path/to/gesture.csv

LIVE     (trigger the device, capture, predict in real time):
    python predict.py --port COM3          # Windows
    python predict.py --port /dev/ttyUSB0  # Linux / Mac
    python predict.py --port /dev/ttyUSB0 --baud 115200

The live mode sends the 't' command to the firmware, reads the 1-second
recording it streams back, and prints the predicted gesture + confidence.
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pickle

MODEL_PATH = Path(__file__).parent / "model_svm.pkl"  # overridden by --model flag
AXIS_COLS  = ["ax", "ay", "az", "gx", "gy", "gz"]

# Gyro columns are indices 3-5. If the peak gyro magnitude is below this
# threshold (°/s) the data is considered resting noise — no prediction made.
MOTION_THRESHOLD = 50.0  # adjust down if your gestures are slow

# ---------------------------------------------------------------------------
# Load model
# ---------------------------------------------------------------------------

def load_model(model_path: Path = MODEL_PATH):
    if not model_path.exists():
        print(f"ERROR: model not found at {model_path}")
        print("Run train_svm.py first.")
        sys.exit(1)
    with open(model_path, "rb") as fh:
        bundle = pickle.load(fh)
    return bundle["pipeline"], bundle["gesture_classes"]


# ---------------------------------------------------------------------------
# Feature extraction  (must match train_svm.py exactly)
# ---------------------------------------------------------------------------

def extract_features(arr: np.ndarray) -> np.ndarray:
    """arr: (N, 6) → returns (18,) feature vector: max / min / std per axis."""
    return np.concatenate([
        arr.max(axis=0),
        arr.min(axis=0),
        arr.std(axis=0),
    ])


# ---------------------------------------------------------------------------
# Prediction + result display
# ---------------------------------------------------------------------------

def predict_and_print(arr: np.ndarray, pipeline, gesture_classes: list[str],
                      threshold: float = MOTION_THRESHOLD):
    if len(arr) == 0:
        print("ERROR: no data rows found.")
        return

    # Check for actual motion using gyroscope columns (indices 3-5)
    gyro = arr[:, 3:6]
    peak_gyro = float(np.abs(gyro).max())
    if peak_gyro < threshold:
        print(f"\n  [No gesture] Peak gyro {peak_gyro:.1f} °/s is below "
              f"threshold ({threshold:.0f} °/s) — likely resting noise.\n")
        return

    features = extract_features(arr).reshape(1, -1)
    prediction   = pipeline.predict(features)[0]
    gesture_name = gesture_classes[prediction]

    print(f"\n{'='*40}")
    print(f"  Prediction  : {gesture_name.upper()}")

    # Confidence scores (requires probability=True in SVC, which we set)
    try:
        probs = pipeline.predict_proba(features)[0]
        print(f"  Confidence  : {max(probs)*100:.1f}%")
        print(f"\n  All scores:")
        for name, prob in sorted(zip(gesture_classes, probs), key=lambda x: -x[1]):
            bar = "█" * int(prob * 20)
            print(f"    {name:>6}  {prob*100:5.1f}%  {bar}")
    except Exception:
        pass  # probability=False model — skip confidence display

    print(f"{'='*40}\n")


# ---------------------------------------------------------------------------
# Offline mode — read a CSV file
# ---------------------------------------------------------------------------

def test_file(path: str, pipeline, gesture_classes):
    p = Path(path)
    if not p.exists():
        print(f"ERROR: file not found: {p}")
        sys.exit(1)

    try:
        arr = np.loadtxt(p, delimiter=",", skiprows=1, dtype=np.float32)
    except Exception as e:
        print(f"ERROR reading file: {e}")
        sys.exit(1)

    if arr.ndim == 1:
        arr = arr.reshape(1, -1)

    print(f"File    : {p.name}")
    print(f"Samples : {len(arr)}")
    predict_and_print(arr, pipeline, gesture_classes)


# ---------------------------------------------------------------------------
# Live mode — talk to the device over serial
# ---------------------------------------------------------------------------

def test_live(port: str, baud: int, pipeline, gesture_classes, threshold: float = MOTION_THRESHOLD):
    try:
        import serial
    except ImportError:
        print("ERROR: pyserial not installed. Run:  pip install pyserial")
        sys.exit(1)

    print(f"Opening {port} at {baud} baud …")
    try:
        ser = serial.Serial(port, baud, timeout=2)
    except serial.SerialException as e:
        print(f"ERROR: could not open port: {e}")
        sys.exit(1)

    time.sleep(0.5)            # let device settle
    ser.reset_input_buffer()

    print("Press Enter to capture a gesture, or Ctrl+C to quit.\n")
    try:
        while True:
            input("  >> Press Enter then perform your gesture … ")
            ser.reset_input_buffer()
            ser.write(b"t")

            rows: list[list[float]] = []
            deadline = time.time() + 5.0
            recording = False

            while time.time() < deadline:
                line = ser.readline().decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                if line == "---START---":
                    recording = True
                    continue
                if line == "---END---":
                    break
                if recording:
                    parts = line.split(",")
                    try:
                        if len(parts) == 8:
                            rows.append([float(v) for v in parts[2:]])
                        elif len(parts) == 6:
                            rows.append([float(v) for v in parts])
                    except ValueError:
                        continue

            if not rows:
                print("  No data received — check firmware is running.\n")
                continue

            arr = np.array(rows, dtype=np.float32)
            print(f"  Samples: {len(arr)}")
            predict_and_print(arr, pipeline, gesture_classes, threshold=threshold)

    except KeyboardInterrupt:
        print("\nExiting.")
    finally:
        ser.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Test the trained SVM gesture model.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "file", nargs="?",
        help="Path to a CSV file for offline testing.",
    )
    parser.add_argument(
        "--port", default=None,
        help="Serial port for live device testing (e.g. COM3 or /dev/ttyUSB0).",
    )
    parser.add_argument(
        "--model", default=None,
        help="Path to model_svm.pkl (default: same folder as this script)."
    )
    parser.add_argument(
        "--baud", type=int, default=115200,
        help="Baud rate (default: 115200).",
    )
    parser.add_argument(
        "--threshold", type=float, default=MOTION_THRESHOLD,
        help=f"Min peak gyro (°/s) to count as a gesture (default: {MOTION_THRESHOLD})."
    )
    args = parser.parse_args()

    if not args.file and not args.port:
        parser.print_help()
        sys.exit(0)

    model_path = Path(args.model) if args.model else MODEL_PATH
    pipeline, gesture_classes = load_model(model_path)

    if args.file:
        test_file(args.file, pipeline, gesture_classes)
    elif args.port:
        test_live(args.port, args.baud, pipeline, gesture_classes, threshold=args.threshold)


if __name__ == "__main__":
    main()