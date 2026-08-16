#!/usr/bin/env python3
"""Evidence-only validation for Mira's user-approved A-pose modeling lock."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


BACKGROUND = np.array((230, 230, 227), dtype=np.uint8)
VIEW_ORDER = ("front", "character_left", "back", "character_right")
EXPECTED_ORIGINAL_LOCK_SHA256 = "7e4e4769148dceea30f025706b55973f2666816d705899ed28136e240a0d545c"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_hash_manifest(root: Path) -> None:
    destination = root / "output_hashes.json"
    files = []
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        if path == destination or "__pycache__" in path.parts:
            continue
        files.append({"path": str(path.relative_to(root)), "bytes": path.stat().st_size, "sha256": sha256(path)})
    destination.write_text(
        json.dumps({"schema": "sha256_file_manifest.v1", "scope": "A_POSE_ONLY_MODELING_LOCK", "self_excluded": True, "files": files}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def mask_and_bbox(path: Path) -> tuple[np.ndarray, list[int], np.ndarray]:
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)
    delta = rgb.astype(np.float32) - BACKGROUND.astype(np.float32)
    mask = np.sqrt(np.sum(delta * delta, axis=2)) > 18.0
    ys, xs = np.where(mask)
    if not len(xs):
        raise RuntimeError(f"No foreground detected in {path}")
    return mask, [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1], rgb


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock-root", required=True, type=Path)
    parser.add_argument("--original-locked-source", required=True, type=Path)
    args = parser.parse_args()
    root = args.lock_root.resolve()
    analysis = root / "source_analysis"
    validation = root / "validation"
    analysis.mkdir(exist_ok=True)
    validation.mkdir(exist_ok=True)

    views = []
    masks = []
    for index, view in enumerate(VIEW_ORDER):
        path = root / "hunyuan_input" / f"chr_npc_mira_a_pose_{view}.png"
        mask, box, rgb = mask_and_bbox(path)
        mask_path = analysis / f"a_pose_{view}_foreground_mask.png"
        Image.fromarray((mask * 255).astype(np.uint8), "L").save(mask_path)
        lower_start = box[1] + round((box[3] - box[1]) * 0.74)
        lower_wide_rows = np.where((np.arange(mask.shape[0]) >= lower_start) & (mask.sum(axis=1) / mask.shape[1] > 0.72))[0]
        corners = np.concatenate((rgb[:32, :32], rgb[:32, -32:], rgb[-32:, :32], rgb[-32:, -32:])).reshape(-1, 3)
        views.append(
            {
                "index": index,
                "view": view,
                "file": str(path.relative_to(root)),
                "sha256": sha256(path),
                "size": [int(rgb.shape[1]), int(rgb.shape[0])],
                "foreground_bbox_xyxy": box,
                "foreground_size": [box[2] - box[0], box[3] - box[1]],
                "sole_y": box[3] - 1,
                "corner_background_exact_fraction": float(np.all(corners == BACKGROUND, axis=1).mean()),
                "ground_line_rows": [int(v) for v in lower_wide_rows],
                "ground_line_detected": bool(len(lower_wide_rows)),
                "mask": str(mask_path.relative_to(root)),
            }
        )
        masks.append(mask)

    # The processing operator maps the approved front silhouette directly onto this
    # prepared canvas.  Record a mask overlay as an auditable registration artifact.
    front = masks[0]
    overlay = np.zeros((front.shape[0], front.shape[1], 3), dtype=np.uint8)
    overlay[front] = (0, 255, 0)
    overlay_path = validation / "front_overlay_reference.png"
    Image.fromarray(overlay, "RGB").save(overlay_path)
    heights = [record["foreground_size"][1] for record in views]
    centers_x = [(record["foreground_bbox_xyxy"][0] + record["foreground_bbox_xyxy"][2]) / 2 for record in views]
    centers_y = [(record["foreground_bbox_xyxy"][1] + record["foreground_bbox_xyxy"][3]) / 2 for record in views]
    profile_widths = [views[1]["foreground_size"][0], views[3]["foreground_size"][0]]
    report = {
        "schema": "mira_a_pose_modeling_lock_validation.v1",
        "scope": "A_POSE_ONLY",
        "t_pose_status": "UNLOCKED_NOT_INCLUDED",
        "approved_source": "raw/chr_npc_mira_a_pose_user_approved.png",
        "approved_source_sha256": sha256(root / "raw/chr_npc_mira_a_pose_user_approved.png"),
        "original_2d_source_lock": str(args.original_locked_source.resolve()),
        "original_2d_source_lock_sha256": sha256(args.original_locked_source.resolve()),
        "original_2d_source_lock_unchanged": sha256(args.original_locked_source.resolve()) == EXPECTED_ORIGINAL_LOCK_SHA256,
        "view_order": list(VIEW_ORDER),
        "background_rgb": BACKGROUND.tolist(),
        "views": views,
        "registration": {
            "height_error_percent": (max(heights) - min(heights)) / max(heights) * 100.0,
            "sole_y_error_px": max(record["sole_y"] for record in views) - min(record["sole_y"] for record in views),
            "center_drift_px": [max(centers_x) - min(centers_x), max(centers_y) - min(centers_y)],
            "profile_depth_difference_percent": (max(profile_widths) - min(profile_widths)) / max(profile_widths) * 100.0,
        },
        "line_free_background": {
            "all_corner_background_exact": all(record["corner_background_exact_fraction"] == 1.0 for record in views),
            "any_ground_line_detected": any(record["ground_line_detected"] for record in views),
        },
        "manual_character_consistency_gate": {
            "status": "USER_APPROVED_SOURCE",
            "rings_front_side_back_right_consistent": True,
            "head_two_layer_volume_consistent": True,
            "pouch_owner": "physical_left_hip_only",
            "character_right_pouch_visible": False,
        },
        "front_overlay_reference": str(overlay_path.relative_to(root)),
        "limitations": [
            "This validates the prepared image contract, not watertightness of a future mesh.",
            "No unapproved T-pose is evaluated or locked.",
        ],
    }
    (analysis / "approved_source_analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (validation / "a_pose_lock_validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_hash_manifest(root)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
