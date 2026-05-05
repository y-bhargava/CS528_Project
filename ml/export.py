"""
export.py — export trained classifier + scaler to esp/main/svm_model.h.

Supports:
  - LDA (native export implemented here, no micromlgen needed)
  - SVM (via micromlgen if installed)
"""

from pathlib import Path
import pickle
import sys

PKL_PATH = Path("ml/model_svm.pkl")
OUT_PATH = Path("esp/main/svm_model.h")


def _format_float_array(values: list[float]) -> str:
    return ", ".join(f"{float(v):.8f}f" for v in values)


def _render_scaler_block(mean: list[float], std: list[float], n_features: int) -> str:
    return f"""
// ---------------------------------------------------------------------------
// Scaler parameters exported from StandardScaler (n_features={n_features})
// Apply scale_features() on your float[{n_features}] array BEFORE calling
// classifier.predict().
// ---------------------------------------------------------------------------
static const float SCALER_MEAN[{n_features}] = {{
    {_format_float_array(mean)}
}};

static const float SCALER_STD[{n_features}] = {{
    {_format_float_array(std)}
}};

inline void scale_features(float* features) {{
    for (int i = 0; i < {n_features}; i++) {{
        features[i] = (features[i] - SCALER_MEAN[i]) / SCALER_STD[i];
    }}
}}
"""


def _export_lda(clf) -> str:
    if not hasattr(clf, "coef_") or not hasattr(clf, "intercept_") or not hasattr(clf, "classes_"):
        raise ValueError("LDA export requires coef_, intercept_, and classes_.")

    coef = clf.coef_
    intercept = clf.intercept_
    class_ids = clf.classes_

    if coef.ndim != 2:
        raise ValueError(f"Unexpected LDA coef_ shape: {coef.shape}")

    n_classes, n_features = coef.shape
    if len(intercept) != n_classes:
        raise ValueError("LDA intercept length does not match number of classes.")
    if len(class_ids) != n_classes:
        raise ValueError("LDA classes length does not match number of classes.")

    coef_rows = ",\n        ".join(
        "{ " + _format_float_array(row.tolist()) + " }" for row in coef
    )
    intercept_row = _format_float_array(intercept.tolist())
    classes_row = ", ".join(str(int(c)) for c in class_ids.tolist())

    return f"""#pragma once
#include <cfloat>
namespace Eloquent {{
    namespace ML {{
        namespace Port {{
            class LDA {{
                public:
                    int predict(float *x) {{
                        float best_score = -FLT_MAX;
                        int best_idx = 0;

                        for (int c = 0; c < {n_classes}; c++) {{
                            float score = INTERCEPT[c];
                            for (int i = 0; i < {n_features}; i++) {{
                                score += COEF[c][i] * x[i];
                            }}
                            if (score > best_score) {{
                                best_score = score;
                                best_idx = c;
                            }}
                        }}

                        return CLASS_IDS[best_idx];
                    }}

                protected:
                    static constexpr float COEF[{n_classes}][{n_features}] = {{
                        {coef_rows}
                    }};

                    static constexpr float INTERCEPT[{n_classes}] = {{
                        {intercept_row}
                    }};

                    static constexpr int CLASS_IDS[{n_classes}] = {{
                        {classes_row}
                    }};
            }};
        }}
    }}
}}
"""


def _export_svm(clf) -> str:
    try:
        from micromlgen import port
    except ImportError as exc:
        raise RuntimeError(
            "micromlgen is required for SVM export. Install it or train with --model-type lda."
        ) from exc

    return port(clf)


def main() -> int:
    with open(PKL_PATH, "rb") as f:
        bundle = pickle.load(f)

    pipeline = bundle["pipeline"]
    scaler = pipeline.named_steps["scaler"]
    model_type = bundle.get("model_type", "svm")
    clf = pipeline.named_steps.get("clf")
    if clf is None:
        clf = pipeline.named_steps.get("svm")
    if clf is None:
        raise RuntimeError(f"Could not find classifier step in pipeline: {list(pipeline.named_steps.keys())}")

    scaler_mean = scaler.mean_.tolist()
    scaler_std = scaler.scale_.tolist()
    n_features = len(scaler_mean)

    if model_type == "lda":
        model_cpp = _export_lda(clf)
    elif model_type == "svm":
        model_cpp = _export_svm(clf)
    else:
        raise RuntimeError(f"Unsupported model_type='{model_type}'.")

    out = model_cpp + _render_scaler_block(scaler_mean, scaler_std, n_features)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(out)

    print(f"Exported {model_type.upper()} + scaler ({n_features} features) -> {OUT_PATH}")
    print(f"Gesture classes: {bundle['gesture_classes']}")
    print(f"Scaler mean[:3]: {[round(v, 4) for v in scaler_mean[:3]]}")
    print(f"Scaler std[:3]:  {[round(v, 4) for v in scaler_std[:3]]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
