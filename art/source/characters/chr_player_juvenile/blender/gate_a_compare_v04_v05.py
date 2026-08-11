"""Fair Gate A silhouette-IoU A/B: Rodin v04 vs Hunyuan v05 under ONE mask method.

Both candidates' clay views are run through the same absolute-distance silhouette extraction and the
same brute-force orientation matching against the locked concept four-view. This makes the two mean
IoU numbers directly comparable (the Rodin values previously recorded used an earlier, directional
threshold that is not comparable on the light-model/dark-bg clay renders).
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import cv2
import numpy as np


PROJECT = Path(__file__).resolve().parents[5]
REF_DIR = PROJECT / "art/source/characters/chr_player_juvenile/source_locked_v04/reference"
CONCEPT = {
    "front": REF_DIR / "figure_view_0.png",
    "left": REF_DIR / "figure_view_1.png",
    "back": REF_DIR / "figure_view_2.png",
    "right": REF_DIR / "figure_view_3.png",
}
CANDIDATES = {
    "rodin_v04": {
        "ny": PROJECT / "art/source/characters/chr_player_juvenile/source_locked_v04/validation/rodin_ny_clay.png",
        "px": PROJECT / "art/source/characters/chr_player_juvenile/source_locked_v04/validation/rodin_px_clay.png",
        "py": PROJECT / "art/source/characters/chr_player_juvenile/source_locked_v04/validation/rodin_py_clay.png",
        "nx": PROJECT / "art/source/characters/chr_player_juvenile/source_locked_v04/validation/rodin_nx_clay.png",
    },
    "hunyuan_v05": {
        "ny": PROJECT / "art/source/characters/chr_player_juvenile/source_locked_v05/validation/hunyuan_mv_ny_clay.png",
        "px": PROJECT / "art/source/characters/chr_player_juvenile/source_locked_v05/validation/hunyuan_mv_px_clay.png",
        "py": PROJECT / "art/source/characters/chr_player_juvenile/source_locked_v05/validation/hunyuan_mv_py_clay.png",
        "nx": PROJECT / "art/source/characters/chr_player_juvenile/source_locked_v05/validation/hunyuan_mv_nx_clay.png",
    },
}
OUT = PROJECT / "art/source/characters/chr_player_juvenile/source_locked_v05/GATE_A_COMPARE.json"


def largest_component(mask: np.ndarray) -> np.ndarray:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if count <= 1:
        return mask
    index = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return np.where(labels == index, 255, 0).astype(np.uint8)


def silhouette(image: np.ndarray, dist_thresh: float = 28.0) -> np.ndarray:
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


def score_candidate(ref_masks: dict, clay_paths: dict) -> dict:
    clay_keys = list(clay_paths.keys())
    concept_keys = list(ref_masks.keys())
    ren = {k: normalize_height(silhouette(cv2.imread(str(p), cv2.IMREAD_COLOR))) for k, p in clay_paths.items()}
    matrix = {ck: {rk: round(iou(ren[ck], ref_masks[rk]), 4) for rk in concept_keys} for ck in clay_keys}
    best = None
    for perm in itertools.permutations(concept_keys):
        total = sum(matrix[ck][perm[i]] for i, ck in enumerate(clay_keys))
        if best is None or total > best[0]:
            best = (total, perm)
    best_total, best_perm = best
    mapping = {clay_keys[i]: best_perm[i] for i in range(4)}
    per_view = {best_perm[i]: {"clay_view": clay_keys[i], "iou": matrix[clay_keys[i]][best_perm[i]]}
                for i in range(4)}
    return {"iou_matrix": matrix, "mapping_clay_to_concept": mapping,
            "mean_iou": round(best_total / 4, 4), "per_view": per_view}


def main() -> None:
    ref = {k: normalize_height(silhouette(cv2.imread(str(p), cv2.IMREAD_COLOR))) for k, p in CONCEPT.items()}
    results = {}
    for name, paths in CANDIDATES.items():
        missing = [str(p) for p in paths.values() if not p.exists()]
        if missing:
            results[name] = {"skipped": "missing clay renders", "missing": missing}
        else:
            results[name] = score_candidate(ref, paths)
    report = {"schema": "gate_a_compare_v04_v05.v1", "method": "absolute-distance silhouette, 1024 canvas, brute-force orientation", "candidates": results}
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("GATE_A_COMPARE", json.dumps(report))


main()
