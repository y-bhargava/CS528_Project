"""
Benchmark 5 classifiers on the gesture IMU dataset (18 features, 5 classes, 500 samples).
Compares: SVM RBF (baseline), Random Forest, Gradient Boosting, k-NN, LDA.

To use:
    uv run python ml/benchmark.py
"""

import time
from pathlib import Path

import numpy as np
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import StratifiedKFold
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

# Same config as train_svm.py
GESTURE_CLASSES = ["left", "right", "up", "down", "twist"]
AXIS_COLS       = ["ax", "ay", "az", "gx", "gy", "gz"]
DATA_DIR        = Path(__file__).parent / "data"
N_SPLITS        = 5
RANDOM_STATE    = 42

# Data Loading and Feature extraction same. as train_svm.py
def _load_csv(path: Path) -> np.ndarray | None:
    try:
        arr = np.loadtxt(path, delimiter=",", skiprows=1, dtype=np.float32)
    except Exception:
        return None
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    return arr if arr.shape[1] == len(AXIS_COLS) and len(arr) > 0 else None


def load_dataset() -> tuple[list[np.ndarray], np.ndarray]:
    X_list, y_list = [], []
    for label_idx, gesture in enumerate(GESTURE_CLASSES):
        gesture_dir = DATA_DIR / gesture
        if not gesture_dir.exists():
            print(f"[data] WARNING: no directory '{gesture}' — skipping")
            continue
        files = sorted(gesture_dir.glob("*.csv"))
        loaded = 0
        for path in files:
            arr = _load_csv(path)
            if arr is None:
                continue
            X_list.append(arr)
            y_list.append(label_idx)
            loaded += 1
        print(f"[data]  {gesture:>6}: {loaded} samples")
    return X_list, np.array(y_list, dtype=np.int32)


def extract_features(window: np.ndarray) -> np.ndarray:
    """18 features: max, min, std for each of 6 axes."""
    return np.concatenate([
        window.max(axis=0),
        window.min(axis=0),
        window.std(axis=0),
    ])


def extract_all_features(X: list[np.ndarray]) -> np.ndarray:
    return np.stack([extract_features(w) for w in X])


def build_models() -> list[tuple[str, object]]:
    return [
        (
            "SVM RBF (baseline)",
            Pipeline([
                ("scaler", StandardScaler()),
                ("clf",    SVC(C=1.0, kernel="rbf", gamma=0.001,
                               probability=True, random_state=RANDOM_STATE)),
            ]),
        ),
        (
            "Random Forest",
            RandomForestClassifier(n_estimators=200, max_features="sqrt",
                                   random_state=RANDOM_STATE, n_jobs=-1),
        ),
        (
            "Gradient Boosting",
            GradientBoostingClassifier(n_estimators=200, learning_rate=0.1,
                                       max_depth=3, random_state=RANDOM_STATE),
        ),
        (
            "k-NN (k=5)",
            Pipeline([
                ("scaler", StandardScaler()),
                ("clf",    KNeighborsClassifier(n_neighbors=5, weights="distance",
                                                metric="euclidean")),
            ]),
        ),
        (
            "LDA",
            Pipeline([
                ("scaler", StandardScaler()),
                ("clf",    LinearDiscriminantAnalysis(solver="svd")),
            ]),
        ),
    ]

def benchmark(X: np.ndarray, y: np.ndarray) -> list[dict]:
    cv = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)
    models = build_models()
    results = []

    for name, model in models:
        fold_accs, fold_f1s = [], []
        fit_times, pred_times = [], []
        all_y_true, all_y_pred = [], []

        for train_idx, test_idx in cv.split(X, y):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            t0 = time.perf_counter()
            model.fit(X_train, y_train)
            fit_times.append(time.perf_counter() - t0)

            t0 = time.perf_counter()
            y_pred = model.predict(X_test)
            pred_times.append(time.perf_counter() - t0)

            fold_accs.append((y_pred == y_test).mean())
            fold_f1s.append(f1_score(y_test, y_pred, average="macro", zero_division=0))
            all_y_true.extend(y_test)
            all_y_pred.extend(y_pred)

        model.fit(X, y)

        results.append({
            "name":       name,
            "acc_mean":   float(np.mean(fold_accs)),
            "acc_std":    float(np.std(fold_accs)),
            "f1_mean":    float(np.mean(fold_f1s)),
            "fit_time":   float(np.sum(fit_times)),
            "pred_time":  float(np.sum(pred_times)),
            "y_true":     all_y_true,
            "y_pred":     all_y_pred,
            "model":      model,
        })

        print(f"  [{name}] acc={np.mean(fold_accs):.4f} ± {np.std(fold_accs):.4f}  "
              f"f1={np.mean(fold_f1s):.4f}  "
              f"fit={np.sum(fit_times):.3f}s  pred={np.sum(pred_times)*1000:.1f}ms")

    return results

SEP  = "─" * 73
HEAD = f"{'Model':<24} {'Acc (mean±std)':>18}  {'Macro F1':>9}  {'Fit(s)':>7}  {'Pred(ms)':>9}"

def print_summary(results: list[dict]) -> None:
    print(f"\n{SEP}")
    print(HEAD)
    print(SEP)

    best = max(results, key=lambda r: r["acc_mean"])
    for r in results:
        marker = " ◀ best" if r["name"] == best["name"] else ""
        print(
            f"  {r['name']:<22} "
            f"{r['acc_mean']:.4f} ± {r['acc_std']:.4f}  "
            f"{r['f1_mean']:>9.4f}  "
            f"{r['fit_time']:>7.3f}  "
            f"{r['pred_time']*1000:>8.1f}ms"
            f"{marker}"
        )
    print(SEP)


def print_per_class(result: dict) -> None:
    print(f"\nPer-class report (5-fold aggregated) — {result['name']}:")
    print(classification_report(
        result["y_true"], result["y_pred"],
        target_names=GESTURE_CLASSES, digits=3,
    ))


def print_confusion(result: dict) -> None:
    from sklearn.metrics import confusion_matrix
    cm = confusion_matrix(result["y_true"], result["y_pred"])
    col_w = 8
    print(f"Confusion matrix — {result['name']}:")
    header = f"{'':10}" + "".join(f"{g:>{col_w}}" for g in GESTURE_CLASSES)
    print(header)
    for i, row in enumerate(cm):
        cells = "".join(f"{v:>{col_w}}" for v in row)
        print(f"  {GESTURE_CLASSES[i]:<8}{cells}")
    print()

def main() -> None:
    print("=" * 73)
    print(" Gesture Classifier Benchmark — 5 models, 5-fold stratified CV")
    print(f" Dataset: {DATA_DIR}")
    print("=" * 73)

    print("\nLoading dataset...")
    X_raw, y = load_dataset()
    X = extract_all_features(X_raw)
    print(f"\nTotal: {len(X)} samples  |  {X.shape[1]} features  |  {len(GESTURE_CLASSES)} classes\n")

    print("Running CV...\n")
    results = benchmark(X, y)

    print_summary(results)

    best = max(results, key=lambda r: r["acc_mean"])
    print_per_class(best)
    print_confusion(best)

    print("\nPer-class F1 breakdown across all models:")
    per_class_header = f"  {'Model':<24}" + "".join(f"  {g:>6}" for g in GESTURE_CLASSES)
    print(per_class_header)
    print("  " + "─" * (len(per_class_header) - 2))
    for r in results:
        per_cls = f1_score(r["y_true"], r["y_pred"], average=None,
                           labels=list(range(len(GESTURE_CLASSES))), zero_division=0)
        row = f"  {r['name']:<24}" + "".join(f"  {v:>6.3f}" for v in per_cls)
        print(row)

    print(f"\nBest model: {best['name']}  (acc={best['acc_mean']:.4f})\n")


if __name__ == "__main__":
    main()
