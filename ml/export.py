"""
export.py — export SVM model + scaler to svm_model.h for the ESP32.

The StandardScaler parameters (mean and std per feature) are baked into the
header alongside the micromlgen SVM so the ESP32 applies the same scaling
that training used before calling classifier.predict().
"""

import pickle
import numpy as np
from pathlib import Path
from micromlgen import port

PKL_PATH = Path("ml/model_svm.pkl")
OUT_PATH = Path("esp/main/svm_model.h")

with open(PKL_PATH, "rb") as f:
    bundle = pickle.load(f)

pipeline       = bundle["pipeline"]
scaler         = pipeline.named_steps["scaler"]
svm_model      = pipeline.named_steps["svm"]
gesture_classes = bundle["gesture_classes"]

# Extract scaler parameters (one value per feature, 18 total)
scaler_mean = scaler.mean_.tolist()
scaler_std  = scaler.scale_.tolist()   # scale_ is the std used for transform
n_features  = len(scaler_mean)

# Generate the SVM classifier code from micromlgen
svm_cpp = port(svm_model)

# Build the scaler helper that the firmware calls before predict()
scaler_block = f"""
// ---------------------------------------------------------------------------
// Scaler parameters exported from StandardScaler (n_features={n_features})
// Apply scale_features() on your float[{n_features}] array BEFORE calling
// classifier.predict().
// ---------------------------------------------------------------------------
static const float SCALER_MEAN[{n_features}] = {{
    {', '.join(f'{v:.8f}f' for v in scaler_mean)}
}};

static const float SCALER_STD[{n_features}] = {{
    {', '.join(f'{v:.8f}f' for v in scaler_std)}
}};

inline void scale_features(float* features) {{
    for (int i = 0; i < {n_features}; i++) {{
        features[i] = (features[i] - SCALER_MEAN[i]) / SCALER_STD[i];
    }}
}}
"""

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
with open(OUT_PATH, "w") as f:
    f.write(svm_cpp)
    f.write(scaler_block)

print(f"Exported SVM + scaler ({n_features} features) → {OUT_PATH}")
print(f"Gesture classes: {gesture_classes}")
print(f"Scaler mean[:3]:  {[round(v,4) for v in scaler_mean[:3]]}")
print(f"Scaler std[:3]:   {[round(v,4) for v in scaler_std[:3]]}")