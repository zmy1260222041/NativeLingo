"""Gate A silhouette-IoU review for the Hunyuan v05 multi-view candidate.

Self-contained mask helpers (absolute-distance from the border-inferred background, which works for
both the light-model/dark-bg clay renders and the concept turnarounds). The Hunyuan forward axis is
unknown, so the four positional clay views (ny/px/py/nx) are brute-force matched onto the concept
front/left/back/right views; the best assignment and per-view IoU are reported for direct comparison
with the Rodin v04 baseline.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import cv2
import numpy as np


PROJECT = Path(__file__).resolve().parents[5]
V04_REF = PROJECT / "art/source/characters/chr_player_juvenile/source_locked_v04/reference"
V05_VAL = PROJECT / "art/source/characters/chr_player_juvenile/source_locked_v05/validation"
OUT = PROJECT / "art/source/characters/chr_player_juvenile/source_locked_v05/GATE_A_REVIEW.json"

CONCEPT = {
    "front": V04_REF / "figure_view_0.png",
    "left": V04_REF / "figure_view_1.png",
    "back": V04_REF / "figure_view_2.png",
    "right": V04_REF / "figure_view_3.png",
}
CLAY = {
    "ny": V05_VAL / "hunyuan_mv_ny_clay.png",
    "px": V05_VAL / "hunyuan_mv_px_clay.png",
    "py": V05_VAL / "hunyuan_mv_py_clay.png",
    "nx": V05_VAL / "hunyuan_mv_nx_clay.png",
}
RODIN_BASELINE = {"front": 0.8174, "left": 0.6665, "back": 0.7396, "right": 0.6665}


def largest_component(mask: np.ndarray) -> np.ndarray:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if count <= 1:
        return mask
    index = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return np.where(labels == index, 255, 0).astype(np.uint8)


def silhouette(image: np.ndarray, dist_thresh: float = 28.0) -> np.ndarray:
    """Absolute-distance silhouette: anything farther than thresh from the border-inferred bg."""
    border = np.concatenate((
        image[:12].reshape(-1, 3), image[-12:].reshape(-1, 3),
        image[:, :8].reshape(-1, 3), image[:, -8:].reshape(-1, 3),
    ))
    background = np.median(border.astype(np.float32), axis=0)
    distance = np.linalg.norm(image.astype(np.float32) - background, axis=2)
    mask = np.where(distance > dist_thresh, 255, 0).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    return largest_component(mask)


def normalize_height(mask: np.ndarray, size: int = 1024, height: int = 900) -> np.ndarray:
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return np.zeros((size, size), dtype=np.uint8)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    crop = mask[y0:y1 + 1, x0:x1 + 1]
    scale = height / crop.shape[0]
    width = max(1, int(round(crop.shape[1] * scale)))
    resized = cv2.resize(crop, (width, height), interpolation=cv2.INTER_NEAREST)
    canvas = np.zeros((size, size), dtype=np.uint8)
    left = max(0, (size - width) // 2)
    bottom = 974
    top = bottom - height
    clipped_width = min(width, size - left)
    canvas[top:bottom, left:left + clipped_width] = resized[:, :clipped_width]
    return canvas


def iou(a: np.ndarray, b: np.ndarray) -> float:
    a = a > 0
    b = b > 0
    inter = int(np.logical_and(a, b).sum())
    uni = int(np.logical_or(a, b).sum())
    return float(inter) / float(uni) if uni else 0.0


def main() -> None:
    ref = {k: normalize_height(silhouette(cv2.imread(str(p), cv2.IMREAD_COLOR))) for k, p in CONCEPT.items()}
    ren = {k: normalize_height(silhouette(cv2.imread(str(p), cv2.IMREAD_COLOR))) for k, p in CLAY.items()}

    # diagnostics: raw mask pixel coverage (sanity check against empty masks)
    cov_ref = {k: int((m > 0).sum()) for k, m in ref.items()}
    cov_ren = {k: int((m > 0).sum()) for k, m in ren.items()}

    clay_keys = list(CLAY.keys())
    concept_keys = list(CONCEPT.keys())
    matrix = {ck: {rk: round(iou(ren[ck], ref[rk]), 4) for rk in concept_keys} for ck in clay_keys}

    best = None
    for perm in itertools.permutations(concept_keys):
        total = sum(matrix[ck][perm[i]] for i, ck in enumerate(clay_keys))
        if best is None or total > best[0]:
            best = (total, perm)
    best_total, best_perm = best
    mapping = {clay_keys[i]: best_perm[i] for i in range(4)}
    per_view = {best_perm[i]: {"clay_view": clay_keys[i], "iou": matrix[clay_keys[i]][best_perm[i]],
                               "rodin_v04": RODIN_BASELINE[best_perm[i]]} for i in range(4)}

    report = {
        "schema": "hunyuan_v05_gate_a_review.v1",
        "candidate": "hunyuan_multiview_v3_1 (Tencent Hunyuan3D Pro Model=3.1, front+left+back+right)",
        "baseline": "rodin v04 (front 0.8174 / left 0.6665 / back 0.7396 / right 0.6665)",
        "mask_coverage_pixels_ref": cov_ref,
        "mask_coverage_pixels_ren": cov_ren,
        "iou_matrix_clay_x_concept": matrix,
        "best_orientation_mapping_clay_to_concept": mapping,
        "mean_iou_best": round(best_total / 4, 4),
        "per_view": per_view,
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("HUNYUAN_V05_GATE_A", json.dumps(report))


main()
