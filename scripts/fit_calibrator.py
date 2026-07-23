"""Fit the score calibrator from the speechocean762 feature set (v1.2).

Two mappings are fitted and written to ``backend/core/calibration.json``:

* accuracy: isotonic regression  DTW mean cost -> human accuracy (0-100)
* fluency:  isotonic GAM — per-feature monotone (decreasing) isotonic maps of
            [path_dev, |log rate_ratio|, pause_ratio], blended with weights
            proportional to squared univariate |PCC|. Chosen over plain OLS
            because OLS flips coefficient signs under multicollinearity and
            extrapolates dangerously (a hesitant reader scored higher); the
            GAM is monotone in every feature by construction, so "more
            pauses" can never raise the score. Val PCC within ~0.01-0.03 of
            OLS.

A held-out split reports PCC / Spearman for the new mapping vs the old
hand-set linear map, so the improvement is measurable.

Usage:
    .venv/bin/python -m scripts.fit_calibrator \
        --features data/calibration_features.jsonl
"""
from __future__ import annotations

import argparse
import json

import numpy as np
from sklearn.isotonic import IsotonicRegression


def _pcc(a: np.ndarray, b: np.ndarray) -> float:
    if a.std() < 1e-9 or b.std() < 1e-9:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def _rankdata(a: np.ndarray) -> np.ndarray:
    """Average ranks, no scipy dependency."""
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), dtype="float64")
    ranks[order] = np.arange(len(a), dtype="float64")
    # average ties
    sa = a[order]
    i = 0
    while i < len(sa):
        j = i
        while j + 1 < len(sa) and sa[j + 1] == sa[i]:
            j += 1
        if j > i:
            ranks[order[i : j + 1]] = ranks[order[i : j + 1]].mean()
        i = j + 1
    return ranks


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    return _pcc(_rankdata(a), _rankdata(b))


def _old_lin_map(x: np.ndarray, good: float = 0.10, bad: float = 0.55) -> np.ndarray:
    return np.clip(100.0 * (bad - x) / (bad - good), 0.0, 100.0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="data/calibration_features.jsonl")
    ap.add_argument("--out", default="backend/core/calibration.json")
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.features)]
    rows = [r for r in rows if r["human_accuracy"] is not None]
    print(f"{len(rows)} rows")

    rng = np.random.RandomState(42)
    perm = rng.permutation(len(rows))
    n_fit = int(0.8 * len(rows))
    fit_idx, val_idx = perm[:n_fit], perm[n_fit:]

    cost = np.array([r["cost"] for r in rows])
    acc_y = np.array([r["human_accuracy"] for r in rows]) * 10.0  # -> 0..100
    flu_y = np.array([r["human_fluency"] for r in rows]) * 10.0
    FLU_FEATS = ["path_dev", "lograte", "pause_ratio"]
    F = np.array(
        [
            [
                r["path_dev"],
                abs(np.log(max(r["rate_ratio"], 1e-3))),
                r["pause_ratio"],
            ]
            for r in rows
        ]
    )

    # --- accuracy: isotonic (cost up => score down) ---
    iso = IsotonicRegression(increasing=False, out_of_bounds="clip")
    iso.fit(cost[fit_idx], acc_y[fit_idx])

    # --- fluency: isotonic GAM (per-feature monotone maps, PCC^2 weights) ---
    flu_isos, flu_w = [], []
    for j in range(F.shape[1]):
        fiso = IsotonicRegression(increasing=False, out_of_bounds="clip")
        fiso.fit(F[fit_idx, j], flu_y[fit_idx])
        flu_isos.append(fiso)
        flu_w.append(abs(_pcc(F[fit_idx, j], flu_y[fit_idx])) ** 2)
    wsum = sum(flu_w)
    flu_w = [w / wsum for w in flu_w]

    def predict_acc(c: np.ndarray) -> np.ndarray:
        return np.clip(iso.predict(c), 0.0, 100.0)

    def predict_flu(f: np.ndarray) -> np.ndarray:
        out = np.zeros(len(f))
        for j, fiso in enumerate(flu_isos):
            out += flu_w[j] * np.clip(fiso.predict(f[:, j]), 0.0, 100.0)
        return np.clip(out, 0.0, 100.0)

    for name, idx in (("fit", fit_idx), ("val", val_idx)):
        old = _old_lin_map(cost[idx])
        new = predict_acc(cost[idx])
        print(
            f"accuracy  [{name}] old-PCC {_pcc(old, acc_y[idx]):.3f} "
            f"new-PCC {_pcc(new, acc_y[idx]):.3f} "
            f"new-Spearman {_spearman(new, acc_y[idx]):.3f}"
        )
        old_f = np.clip(100.0 * (1.0 - F[idx, 0] / 0.15), 0, 100)
        new_f = predict_flu(F[idx])
        print(
            f"fluency   [{name}] old-PCC {_pcc(old_f, flu_y[idx]):.3f} "
            f"new-PCC {_pcc(new_f, flu_y[idx]):.3f} "
            f"new-Spearman {_spearman(new_f, flu_y[idx]):.3f}"
        )

    calib = {
        "meta": {
            "source": "mispeech/speechocean762 + macOS say reference",
            "encoder_layers": [6, 7, 8, 9],
            "n_rows": len(rows),
            "n_fit": int(n_fit),
            "accuracy_val_pcc": round(_pcc(predict_acc(cost[val_idx]), acc_y[val_idx]), 4),
            "fluency_val_pcc": round(_pcc(predict_flu(F[val_idx]), flu_y[val_idx]), 4),
        },
        "accuracy_isotonic": {
            "x": [round(float(v), 6) for v in iso.X_thresholds_],
            "y": [round(float(v), 3) for v in iso.y_thresholds_],
        },
        "fluency_gam": {
            "components": [
                {
                    "feature": name,
                    "weight": round(float(w), 4),
                    "x": [round(float(v), 6) for v in fiso.X_thresholds_],
                    "y": [round(float(v), 3) for v in fiso.y_thresholds_],
                }
                for name, w, fiso in zip(FLU_FEATS, flu_w, flu_isos)
            ]
        },
    }
    with open(args.out, "w") as f:
        json.dump(calib, f, indent=2)
    print(f"wrote {args.out}")
    print("fluency weights:", {n: round(float(w), 3) for n, w in zip(FLU_FEATS, flu_w)})


if __name__ == "__main__":
    main()
