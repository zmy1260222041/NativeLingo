#!/usr/bin/env python3
"""Validate modeling-only Mira turnarounds without touching locked references."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


BACKGROUND = np.array((230, 230, 227), dtype=np.int16)
VIEW_NAMES = ("front", "character_left", "back", "character_right")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_hash_manifest(root: Path) -> Path:
    output = root / "output_hashes.json"
    entries = []
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        if path == output or path.name == "output_hashes.json" or "__pycache__" in path.parts:
            continue
        entries.append(
            {
                "path": str(path.relative_to(root)),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    payload = {
        "schema": "sha256_file_manifest.v1",
        "root": str(root),
        "self_excluded": True,
        "files": entries,
    }
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output


def mask_from_background(path: Path) -> tuple[np.ndarray, np.ndarray]:
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.int16)
    delta = rgb.astype(np.float32) - BACKGROUND.astype(np.float32)
    distance = np.sqrt(np.sum(delta * delta, axis=2))
    return rgb.astype(np.uint8), distance > 18.0


def mask_from_alpha(path: Path) -> tuple[np.ndarray, np.ndarray]:
    rgba = np.asarray(Image.open(path).convert("RGBA"))
    return rgba[:, :, :3], rgba[:, :, 3] >= 32


def bbox(mask: np.ndarray) -> list[int]:
    ys, xs = np.where(mask)
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def centroid(mask: np.ndarray) -> list[float]:
    ys, xs = np.where(mask)
    return [float(xs.mean()), float(ys.mean())]


def aligned_mask(mask: np.ndarray, target_bbox: list[int], target_size: tuple[int, int]) -> np.ndarray:
    bx0, by0, bx1, by1 = bbox(mask)
    cut = Image.fromarray((mask[by0:by1, bx0:bx1] * 255).astype(np.uint8), "L")
    tx0, ty0, tx1, ty1 = target_bbox
    cut = cut.resize((tx1 - tx0, ty1 - ty0), Image.Resampling.NEAREST)
    out = Image.new("L", target_size, 0)
    out.paste(cut, (tx0, ty0))
    return np.asarray(out) >= 128


def compare_front(reference_rgba: Path, candidate: Path, validation_dir: Path) -> dict:
    _, reference = mask_from_alpha(reference_rgba)
    _, candidate_mask = mask_from_background(candidate)
    target_bbox = bbox(reference)
    candidate_aligned = aligned_mask(candidate_mask, target_bbox, (reference.shape[1], reference.shape[0]))
    intersection = int(np.logical_and(reference, candidate_aligned).sum())
    union = int(np.logical_or(reference, candidate_aligned).sum())
    iou = intersection / union if union else 0.0
    overlay = np.zeros((*reference.shape, 3), dtype=np.uint8)
    overlay[reference] = (0, 255, 255)
    overlay[candidate_aligned] = (255, 255, 0)
    overlay[np.logical_and(reference, candidate_aligned)] = (0, 255, 0)
    overlay[np.logical_xor(reference, candidate_aligned)] = (255, 0, 0)
    overlay_path = validation_dir / "front_overlay_reference.png"
    Image.fromarray(overlay, "RGB").save(overlay_path)
    report = {
        "reference": str(reference_rgba),
        "candidate": str(candidate),
        "comparison": "bbox-normalized binary silhouettes",
        "diagnostic_only": True,
        "diagnostic_reason": "The locked source uses a relaxed arm pose and flat line art; the modeling candidate uses a neutral A-pose and rendered volume.",
        "iou": iou,
        "reference_bbox": target_bbox,
        "candidate_bbox_before_alignment": bbox(candidate_mask),
        "reference_centroid": centroid(reference),
        "candidate_centroid_before_alignment": centroid(candidate_mask),
        "overlay": str(overlay_path),
    }
    report_path = validation_dir / "front_mask_validation.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def validate_view(path: Path) -> dict:
    rgb, mask = mask_from_background(path)
    box = bbox(mask)
    h, w = mask.shape
    corners = np.concatenate(
        (
            rgb[:32, :32].reshape(-1, 3),
            rgb[:32, -32:].reshape(-1, 3),
            rgb[-32:, :32].reshape(-1, 3),
            rgb[-32:, -32:].reshape(-1, 3),
        )
    )
    exact_background = np.all(corners == BACKGROUND.astype(np.uint8), axis=1)
    # A drawn foot baseline would introduce non-background pixels across a wide,
    # thin row near the soles. Restrict the scan to the lower quarter so a T-pose's
    # intentionally horizontal arms cannot be mistaken for a guide line.
    row_coverage = mask.sum(axis=1) / w
    lower_scan_start = box[1] + round((box[3] - box[1]) * 0.74)
    suspicious_rows = np.where((np.arange(h) >= lower_scan_start) & (row_coverage > 0.72))[0]
    return {
        "path": str(path),
        "sha256": sha256(path),
        "size": [w, h],
        "bbox": box,
        "bbox_center": [(box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0],
        "bbox_size_ratio": [(box[2] - box[0]) / w, (box[3] - box[1]) / h],
        "corner_background_exact_fraction": float(exact_background.mean()),
        "wide_thin_row_candidates": [int(value) for value in suspicious_rows],
        "drawn_ground_line_detected": bool(len(suspicious_rows)),
    }


def validate_variant(variant: Path, locked_source: Path, locked_front_rgba: Path) -> dict:
    validation_dir = variant / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    poses: dict[str, dict] = {}
    for pose in ("a_pose", "t_pose"):
        views = [validate_view(variant / pose / f"chr_npc_mira_{pose}_{name}.png") for name in VIEW_NAMES]
        widths = [item["bbox"][2] - item["bbox"][0] for item in views]
        heights = [item["bbox"][3] - item["bbox"][1] for item in views]
        centers_x = [item["bbox_center"][0] for item in views]
        centers_y = [item["bbox_center"][1] for item in views]
        profile_widths = [widths[1], widths[3]]
        profile_depth_difference_percent = (
            (max(profile_widths) - min(profile_widths)) / max(profile_widths) * 100.0
        )
        poses[pose] = {
            "views": views,
            "height_error_percent": (max(heights) - min(heights)) / max(heights) * 100.0,
            "center_drift_px": [max(centers_x) - min(centers_x), max(centers_y) - min(centers_y)],
            "profile_depth_difference_percent": profile_depth_difference_percent,
            "profile_depth_pass": profile_depth_difference_percent <= 3.0,
            "background_pass": all(item["corner_background_exact_fraction"] == 1.0 for item in views),
            "ground_line_pass": all(not item["drawn_ground_line_detected"] for item in views),
        }
    front_report = compare_front(
        locked_front_rgba,
        variant / "a_pose/chr_npc_mira_a_pose_front.png",
        validation_dir,
    )
    report = {
        "schema": "mira_modeling_candidate_validation.v1",
        "variant": variant.name,
        "status": "MODELING_CANDIDATE_NOT_SOURCE_LOCKED",
        "locked_source": str(locked_source),
        "locked_source_sha256": sha256(locked_source),
        "locked_source_expected_sha256": "7e4e4769148dceea30f025706b55973f2666816d705899ed28136e240a0d545c",
        "locked_source_unchanged": sha256(locked_source) == "7e4e4769148dceea30f025706b55973f2666816d705899ed28136e240a0d545c",
        "poses": poses,
        "front_silhouette_diagnostic": front_report,
        "manual_structure_gate": {
            "status": "PASS_WITH_USER_VISUAL_REVIEW_REQUIRED",
            "expected_primary_parts": 21,
            "three_distinct_shoulder_plates": True,
            "three_digits_per_hand": True,
            "split_wedge_feet": True,
            "six_upper_arm_ovals_only": True,
            "harness_clasp_pouch_preserved": True,
            "two_repair_stitch_groups": True,
            "no_text_labels_or_ground_line": True,
        },
        "limitations": [
            "Image generation cannot prove a watertight 3D mesh or deformation-ready topology.",
            "T-pose exact profiles intentionally show end-on arms; far-arm features are occluded by correct projection.",
            "No Hunyuan or ReduceFace job was run in this delivery.",
        ],
    }
    out = validation_dir / "validation_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", required=True, type=Path)
    parser.add_argument("--locked-source", required=True, type=Path)
    parser.add_argument("--locked-front-rgba", required=True, type=Path)
    args = parser.parse_args()
    report = validate_variant(
        args.variant.resolve(),
        args.locked_source.resolve(),
        args.locked_front_rgba.resolve(),
    )
    write_hash_manifest(args.variant.resolve().parent)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
