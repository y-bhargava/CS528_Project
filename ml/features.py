from pathlib import Path

import numpy as np


GESTURE_CLASSES = ["left", "right", "up", "down", "twist"]
AXIS_COLS = ["ax", "ay", "az", "gx", "gy", "gz"]
WINDOW_SIZE = 100


def load_csv_window(path: Path) -> np.ndarray | None:
    """
    Load one gesture CSV and return an (N, 6) float32 array in AXIS_COLS order.

    Accepts the training/export format:
        ax,ay,az,gx,gy,gz

    Also accepts live/debug logs with leading metadata columns:
        timestamp,...,ax,ay,az,gx,gy,gz
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            header = fh.readline().strip().split(",")
    except OSError:
        return None

    try:
        arr = np.loadtxt(path, delimiter=",", skiprows=1, dtype=np.float32)
    except Exception:
        return None

    if arr.ndim == 1:
        arr = arr.reshape(1, -1)

    if len(arr) == 0:
        return None

    if arr.shape[1] == len(AXIS_COLS):
        return arr

    if all(axis in header for axis in AXIS_COLS):
        indices = [header.index(axis) for axis in AXIS_COLS]
        if max(indices) < arr.shape[1]:
            return arr[:, indices]

    return None


def extract_features(window: np.ndarray) -> np.ndarray:
    """
    Extract the 18-feature vector used by training, prediction, and ESP export:
    [max(ax..gz), min(ax..gz), std(ax..gz)].
    """
    if window.ndim != 2 or window.shape[1] != len(AXIS_COLS):
        raise ValueError(
            f"expected window shape (N, {len(AXIS_COLS)}), got {window.shape}"
        )

    return np.concatenate([
        window.max(axis=0),
        window.min(axis=0),
        window.std(axis=0),
        window.mean(axis=0) 
    ])


def extract_all_features(windows: list[np.ndarray]) -> np.ndarray:
    return np.stack([extract_features(window) for window in windows])
