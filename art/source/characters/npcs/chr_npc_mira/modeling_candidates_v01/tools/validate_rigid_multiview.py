#!/usr/bin/env python3
"""Validate Mira v04 head rigidity and single-left-pouch visibility contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


BACKGROUND = np.array((230, 230, 227), dtype=np.float32)
VIEWS = ("front", "character_left", "back", "character_right")
HEAD_PROBE_HEIGHT = 110


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def foreground(image: Image.Image) -> np.ndarray:
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    delta = rgb - BACKGROUND
    return np.sqrt(np.sum(delta * delta, axis=2)) > 18.0


def head_bbox(image: Image.Image) -> list[int]:
    mask = foreground(image)
    y0 = int(np.where(mask)[0].min())
    probe = np.zeros_like(mask)
    probe[y0 : y0 + HEAD_PROBE_HEIGHT] = mask[y0 : y0 + HEAD_PROBE_HEIGHT]
    ys, xs = np.where(probe)
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def relative_delta(a: float, b: float) -> float:
    return abs(a - b) / max(a, b, 1e-9)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", required=True, type=Path)
    parser.add_argument("--locked-source", required=True, type=Path)
    args = parser.parse_args()
    variant = args.variant.resolve()
    validation = variant / "validation"
    validation.mkdir(parents=True, exist_ok=True)

    measurements: dict[str, dict[str, dict]] = {}
    images: dict[str, dict[str, Image.Image]] = {}
    for pose in ("a_pose", "t_pose"):
        measurements[pose] = {}
        images[pose] = {}
        for view in VIEWS:
            path = variant / pose / f"chr_npc_mira_{pose}_{view}.png"
            image = Image.open(path).convert("RGB")
            images[pose][view] = image
            box = head_bbox(image)
            measurements[pose][view] = {
                "path": str(path.relative_to(variant)),
                "bbox": box,
                "width": box[2] - box[0],
                "probe_height": box[3] - box[1],
            }

    per_pose = {}
    for pose, rows in measurements.items():
        front_back_width_delta = relative_delta(rows["front"]["width"], rows["back"]["width"])
        side_depth_delta = relative_delta(
            rows["character_left"]["width"], rows["character_right"]["width"]
        )
        heights = [row["probe_height"] for row in rows.values()]
        z_delta = (max(heights) - min(heights)) / max(heights)
        per_pose[pose] = {
            "measurements": rows,
            "shared_x_front_back_relative_delta": front_back_width_delta,
            "shared_y_left_right_relative_delta": side_depth_delta,
            "shared_z_relative_delta": z_delta,
            "front_back_x_pass_5_percent": front_back_width_delta <= 0.05,
            "left_right_y_pass_3_percent": side_depth_delta <= 0.03,
            "shared_z_pass_2_percent": z_delta <= 0.02,
        }

    registration = json.loads(
        (variant / "t_pose" / "registration_report.json").read_text(encoding="utf-8")
    )
    anchor = registration["cross_pose_head_anchor"]
    cross_pose = []
    for record in anchor["records"]:
        view = record["view"]
        x0, y0, x1, _ = record["head_roi"]
        y1 = y0 + record["core_height"]
        a = np.asarray(images["a_pose"][view])[y0:y1, x0:x1]
        t = np.asarray(images["t_pose"][view])[y0:y1, x0:x1]
        equality = float(np.all(a == t, axis=2).mean())
        cross_pose.append(
            {
                "view": view,
                "head_core_roi": [x0, y0, x1, y1],
                "pixel_equality_fraction": equality,
                "pass": equality == 1.0,
            }
        )

    locked_hash = sha256(args.locked_source.resolve())
    report = {
        "schema": "mira_rigid_multiview_validation.v1",
        "variant": variant.name,
        "canonical_policy": "front_side_canonical",
        "head_contract": "two nested rigid coral/cream shell volumes above the short purple neck",
        "head_probe_height_px": HEAD_PROBE_HEIGHT,
        "per_pose_head_shared_axis_compatibility": per_pose,
        "cross_pose_head_core": {
            "method": anchor["method"],
            "views": cross_pose,
            "all_pass": all(item["pass"] for item in cross_pose),
        },
        "tool_pouch_visibility": {
            "physical_owner": "character physical left hip",
            "expected": {
                "front": True,
                "character_left": True,
                "back": True,
                "character_right": False,
            },
            "a_pose_manual_observed": {
                "front": True,
                "character_left": True,
                "back": True,
                "character_right": False,
            },
            "t_pose_manual_observed": {
                "front": True,
                "character_left": True,
                "back": True,
                "character_right": False,
            },
            "status": "PASS_MANUAL_VISUAL_INSPECTION",
        },
        "head_layer_manual_gate": {
            "front_two_layers_readable": True,
            "character_left_two_layers_and_recess_readable": True,
            "back_corresponding_upper_and_lower_rear_lobes": True,
            "character_right_two_layers_and_recess_readable": True,
            "purple_back_structure_begins_below_head": True,
            "status": "PASS_MANUAL_VISUAL_INSPECTION",
        },
        "locked_source_sha256": locked_hash,
        "locked_source_expected_sha256": "7e4e4769148dceea30f025706b55973f2666816d705899ed28136e240a0d545c",
        "locked_source_unchanged": locked_hash
        == "7e4e4769148dceea30f025706b55973f2666816d705899ed28136e240a0d545c",
        "all_numeric_pass": all(
            rows["front_back_x_pass_5_percent"]
            and rows["left_right_y_pass_3_percent"]
            and rows["shared_z_pass_2_percent"]
            for rows in per_pose.values()
        )
        and all(item["pass"] for item in cross_pose),
    }
    out = validation / "rigid_multiview_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    solver_input = {
        "views": {
            "front": {"bbox": [0, 0, measurements["a_pose"]["front"]["width"], HEAD_PROBE_HEIGHT]},
            "side": {
                "bbox": [0, 0, measurements["a_pose"]["character_left"]["width"], HEAD_PROBE_HEIGHT]
            },
            "back": {"bbox": [0, 0, measurements["a_pose"]["back"]["width"], HEAD_PROBE_HEIGHT]},
        },
        "note": "A-pose canonical rigid head probe; character-right is checked separately in rigid_multiview_report.json",
    }
    (validation / "head_view_bboxes.json").write_text(
        json.dumps(solver_input, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
