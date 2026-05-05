import argparse
import csv
import pickle
import sys
from pathlib import Path

import numpy as np
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GESTURE_CLASSES = ["left", "right", "up", "down", "twist"]

# Column order in the data files
AXIS_COLS = ["ax", "ay", "az", "gx", "gy", "gz"]

DATA_DIR   = Path(__file__).parent / "data"
MODEL_PATH = Path(__file__).parent / "model_svm.pkl"

DEFAULT_C      = 1.0
DEFAULT_KERNEL = "rbf"

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_csv(path: Path) -> np.ndarray | None:
    """
    Read one gesture CSV with header: ax,ay,az,gx,gy,gz
    Returns an (N, 6) float32 array, or None on failure.
    """
    try:
        arr = np.loadtxt(path, delimiter=",", skiprows=1, dtype=np.float32)
    except Exception:
        return None

    if arr.ndim == 1:
        arr = arr.reshape(1, -1)

    if arr.shape[1] != len(AXIS_COLS):
        return None

    return arr if len(arr) > 0 else None


def load_dataset() -> tuple[list[np.ndarray], np.ndarray]:
    X_list: list[np.ndarray] = []
    y_list:  list[int]       = []

    for label_idx, gesture in enumerate(GESTURE_CLASSES):
        gesture_dir = DATA_DIR / gesture
        if not gesture_dir.exists():
            print(f"[data] WARNING: no directory for '{gesture}' — skipping")
            continue

        files = sorted(gesture_dir.glob("*.csv"))
        if not files:
            print(f"[data] WARNING: no CSV files for '{gesture}' — skipping")
            continue

        loaded = 0
        for path in files:
            arr = _load_csv(path)
            if arr is None or len(arr) == 0:
                print(f"[data]   skipped (empty/unreadable): {path.name}")
                continue
            X_list.append(arr)
            y_list.append(label_idx)
            loaded += 1

        print(f"[data] {gesture:>8}: {loaded} files loaded")

    return X_list, np.array(y_list, dtype=np.int32)

# ---------------------------------------------------------------------------
# Feature extraction  —  18 features (matches svm.py)
# ---------------------------------------------------------------------------
# For each of the 6 sensor axes: max, min, std  →  6 × 3 = 18 features.
# These capture the peak excursion, direction (phase), and spread of the
# signal — the three statistics shown to separate the four gesture classes
# in the domain analysis.

def extract_features(window: np.ndarray) -> np.ndarray:
    """
    window : (N, 6) float array — N time steps, 6 sensor axes.
    Returns a (18,) feature vector: [max×6, min×6, std×6].
    """
    return np.concatenate([
        window.max(axis=0),   # 6 values — peak magnitude / direction
        window.min(axis=0),   # 6 values — trough magnitude / direction
        window.std(axis=0),   # 6 values — spread / energy
    ])


def extract_all_features(X: list[np.ndarray]) -> np.ndarray:
    return np.stack([extract_features(w) for w in X])

# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train(c: float, kernel: str) -> None:
    X_raw, y = load_dataset()

    if len(X_raw) == 0:
        print("No training data found. Collect data first.")
        sys.exit(1)

    missing = [g for i, g in enumerate(GESTURE_CLASSES) if (y == i).sum() == 0]
    if missing:
        print(f"ERROR: no samples for gesture(s): {missing}")
        sys.exit(1)

    print(f"\nTotal samples : {len(X_raw)}")
    print(f"Feature vector: 18  (max / min / std for each of {len(AXIS_COLS)} axes)")

    X = extract_all_features(X_raw)   # shape (N, 18)

    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("svm",    SVC(C=c, kernel=kernel, gamma=0.001, probability=True)),
    ])

    cv     = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    scores = cross_val_score(pipeline, X, y, cv=cv, scoring="accuracy")
    print(
        f"[train] 5-fold CV accuracy: {scores.mean():.4f} ± {scores.std():.4f}  "
        f"(per fold: {', '.join(f'{s:.3f}' for s in scores)})"
    )

    pipeline.fit(X, y)

    with open(MODEL_PATH, "wb") as fh:
        pickle.dump(
            {"pipeline": pipeline, "gesture_classes": GESTURE_CLASSES, "axes": AXIS_COLS},
            fh,
        )
    print(f"[train] model saved → {MODEL_PATH}")

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Train SVM gesture classifier (18 features).")
    parser.add_argument(
        "--c", type=float, default=DEFAULT_C,
        help=f"SVM regularisation parameter C (default: {DEFAULT_C}).",
    )
    parser.add_argument(
        "--kernel", default=DEFAULT_KERNEL, choices=["rbf", "linear", "poly"],
        help=f"SVM kernel (default: {DEFAULT_KERNEL}).",
    )
    args = parser.parse_args()
    train(args.c, args.kernel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())