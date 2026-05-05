import argparse
import pickle
import sys
from pathlib import Path

import numpy as np
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

try:
    from features import AXIS_COLS, GESTURE_CLASSES, extract_all_features, load_csv_window
except ImportError:
    from .features import AXIS_COLS, GESTURE_CLASSES, extract_all_features, load_csv_window

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR   = Path(__file__).parent / "data"
MODEL_PATH = Path(__file__).parent / "model_svm.pkl"

DEFAULT_C      = 1.0
DEFAULT_KERNEL = "linear"
DEFAULT_GAMMA  = "0.001"
DEFAULT_MODEL_TYPE = "lda"

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_csv(path: Path) -> np.ndarray | None:
    """
    Read one gesture CSV with header: ax,ay,az,gx,gy,gz
    Returns an (N, 6) float32 array, or None on failure.
    """
    return load_csv_window(path)


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

def train(model_type: str, c: float, kernel: str, gamma: str | float) -> None:
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

    if model_type == "lda":
        clf = LinearDiscriminantAnalysis(solver="svd")
    else:
        clf = SVC(C=c, kernel=kernel, gamma=gamma, probability=True, random_state=42)

    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", clf),
    ])

    cv     = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    scores = cross_val_score(pipeline, X, y, cv=cv, scoring="accuracy")
    print(
        f"[train] {model_type.upper()} 5-fold CV accuracy: {scores.mean():.4f} ± {scores.std():.4f}  "
        f"(per fold: {', '.join(f'{s:.3f}' for s in scores)})"
    )

    pipeline.fit(X, y)

    with open(MODEL_PATH, "wb") as fh:
        pickle.dump(
            {
                "pipeline": pipeline,
                "gesture_classes": GESTURE_CLASSES,
                "axes": AXIS_COLS,
                "feature_order": "max,min,std",
                "window_size": 100,
                "model_type": model_type,
            },
            fh,
        )
    print(f"[train] model saved → {MODEL_PATH}")

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Train gesture classifier (18 features).")
    parser.add_argument(
        "--model-type", default=DEFAULT_MODEL_TYPE, choices=["lda", "svm"],
        help=f"Classifier type (default: {DEFAULT_MODEL_TYPE}).",
    )
    parser.add_argument(
        "--c", type=float, default=DEFAULT_C,
        help=f"SVM regularisation parameter C (default: {DEFAULT_C}, SVM only).",
    )
    parser.add_argument(
        "--kernel", default=DEFAULT_KERNEL, choices=["rbf", "linear", "poly"],
        help=f"SVM kernel (default: {DEFAULT_KERNEL}, SVM only).",
    )
    parser.add_argument(
        "--gamma", default=DEFAULT_GAMMA,
        help=f"SVM gamma for rbf/poly kernels (default: {DEFAULT_GAMMA}, SVM only).",
    )
    args = parser.parse_args()
    try:
        gamma: str | float = float(args.gamma)
    except ValueError:
        gamma = args.gamma
    train(args.model_type, args.c, args.kernel, gamma)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
