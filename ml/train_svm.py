import argparse
import csv
import json
import pickle
import sys
from pathlib import Path

import numpy as np
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

GESTURE_CLASSES = ["swipe_left", "swipe_right", "flick_up", "hold"]
AXES = ["ax", "ay", "az", "gx", "gy", "gz"]
WINDOW_SIZE = 50
N_AXES = len(AXES)

DATA_DIR = Path(__file__).parent / "data"
MODEL_PATH = Path(__file__).parent / "model_svm.pkl"

DEFAULT_C = 10.0
DEFAULT_KERNEL = "rbf"


def _load_csv(path: Path) -> list[list[float]] | None:
    rows: list[list[float]] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        next(reader, None)
        for row in reader:
            try:
                rows.append([float(v) for v in row])
            except ValueError:
                continue
    return rows if rows else None


def load_dataset() -> tuple[list[np.ndarray], np.ndarray]:
    X_list, y_list = [], []

    for label_idx, gesture in enumerate(GESTURE_CLASSES):
        gesture_dir = DATA_DIR / gesture
        if not gesture_dir.exists():
            print(f"No data directory for '{gesture}'")
            continue

        files = sorted(gesture_dir.glob("*.csv"))
        if not files:
            print(f"No CSV files for '{gesture}'")
            continue

        loaded = 0
        for path in files:
            rows = _load_csv(path)
            if rows is None:
                continue
            X_list.append(np.array(rows, dtype=np.float32))
            y_list.append(label_idx)
            loaded += 1

        print(f"[data] {gesture:>12}: {loaded} files")

    if not X_list:
        return [], np.empty(0, dtype=np.int32)

    return X_list, np.array(y_list, dtype=np.int32)



def extract_features(window: np.ndarray) -> np.ndarray:
    mean = window.mean(axis=0)                          
    std = window.std(axis=0)                            
    maximum = window.max(axis=0)                        
    minimum = window.min(axis=0)                        
    rms = np.sqrt((window ** 2).mean(axis=0))           
    return np.concatenate([mean, std, maximum, minimum, rms])  


def extract_all_features(X: list[np.ndarray]) -> np.ndarray:
    return np.stack([extract_features(window) for window in X])


def train(c: float, kernel: str) -> None:
    X_raw, y = load_dataset()

    if len(X_raw) == 0:
        print("No training data found. Need to run collect.py first.")
        sys.exit(1)

    missing = [g for i, g in enumerate(GESTURE_CLASSES) if (y == i).sum() == 0]
    if missing:
        print(f"ERROR: no samples for: {missing}")
        sys.exit(1)

    print(f"Total samples: {len(X_raw)}")

    X = extract_all_features(X_raw)

    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("svm", SVC(C=c, kernel=kernel, probability=True)),
    ])
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    scores = cross_val_score(pipeline, X, y, cv=cv, scoring="accuracy")
    print(
        f"[train] 5-fold CV accuracy: {scores.mean():.4f} ± {scores.std():.4f}  "
        f"(per fold: {', '.join(f'{s:.3f}' for s in scores)})"
    )

    pipeline.fit(X, y)

    with open(MODEL_PATH, "wb") as fh:
        pickle.dump({"pipeline": pipeline, "gesture_classes": GESTURE_CLASSES, "axes": AXES}, fh)
    print(f"[train] model saved → {MODEL_PATH}")

def main() -> int:
    parser = argparse.ArgumentParser(description="Training SVM gesture classifier.")
    parser.add_argument(
        "--c", type=float, default=DEFAULT_C,
        help=f"SVM regularisation parameter C (default: {DEFAULT_C})."
    )
    parser.add_argument(
        "--kernel", default=DEFAULT_KERNEL, choices=["rbf", "linear", "poly"],
        help=f"SVM kernel (default: {DEFAULT_KERNEL})."
    )
    args = parser.parse_args()

    train(args.c, args.kernel)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
