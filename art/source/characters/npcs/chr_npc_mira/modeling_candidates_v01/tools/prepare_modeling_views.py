#!/usr/bin/env python3
"""Prepare Mira modeling-only A/T-pose contact sheets and Hunyuan view images.

The AI-generated source sheets stay immutable inside each variant's ``raw`` folder.
This script performs mechanical processing only: estimate the near-uniform generated
background, key it out, place each detected view on a shared 1024-square canvas, and
compose a line-free four-view contact sheet. It never reads or writes historical NPC
turnarounds and never modifies the source-locked Mira package.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


VIEW_NAMES = ("front", "character_left", "back", "character_right")
BACKGROUND = np.array((230, 230, 227), dtype=np.uint8)  # #E6E6E3
CANVAS_SIZE = 1024
TARGET_HEIGHT = 900


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def estimate_background(rgb: np.ndarray) -> np.ndarray:
    h, w = rgb.shape[:2]
    edge = max(24, min(h, w) // 24)
    samples = np.concatenate(
        (
            rgb[:edge, :edge].reshape(-1, 3),
            rgb[:edge, -edge:].reshape(-1, 3),
            rgb[-edge:, :edge].reshape(-1, 3),
            rgb[-edge:, -edge:].reshape(-1, 3),
        )
    )
    return np.median(samples, axis=0)


def foreground_alpha(rgb: np.ndarray, background: np.ndarray) -> np.ndarray:
    distance = np.sqrt(np.sum((rgb.astype(np.float32) - background) ** 2, axis=2))
    alpha = np.clip((distance - 8.0) * (255.0 / 16.0), 0, 255).astype(np.uint8)
    alpha[distance >= 24.0] = 255
    # Generated studio sheets can contain a soft neutral-gray floor/contact shadow even
    # when the prompt forbids one.  Color-distance keying alone preserves that shadow.
    # Remove only bright/mid-value near-neutral pixels; Mira's dark harness is below the
    # value threshold and her cream, coral and plum materials have appreciable chroma.
    channel_range = np.ptp(rgb.astype(np.int16), axis=2)
    mean_value = rgb.astype(np.float32).mean(axis=2)
    neutral_studio_residue = (channel_range <= 8) & (mean_value >= 108.0)
    alpha[neutral_studio_residue] = 0
    return alpha


def active_runs(alpha: np.ndarray, minimum_width: int = 40) -> list[tuple[int, int]]:
    active = np.where((alpha >= 48).sum(axis=0) > 2)[0]
    if not len(active):
        return []
    runs: list[tuple[int, int]] = []
    start = previous = int(active[0])
    for value in active[1:]:
        value = int(value)
        if value > previous + 1:
            if previous - start + 1 >= minimum_width:
                runs.append((start, previous + 1))
            start = value
        previous = value
    if previous - start + 1 >= minimum_width:
        runs.append((start, previous + 1))
    return runs


def pose_ranges(alpha: np.ndarray, pose: str) -> list[tuple[int, int]]:
    h, w = alpha.shape
    runs = active_runs(alpha)
    if pose == "a_pose":
        if len(runs) == 4:
            return runs
        # A faint generated studio shadow can bridge otherwise isolated figures. Locate
        # four lower bodies, where the diagonal arms cannot cross a view boundary, then
        # split the source sheet at the center midpoints just as for a T-pose.
        lower_runs = active_runs(alpha[round(h * 0.46) :], minimum_width=60)
        if len(lower_runs) != 4:
            raise RuntimeError(
                f"A-pose expected four figures; full={runs}, lower={lower_runs}"
            )
        centers = [(start + end) / 2.0 for start, end in lower_runs]
        splits = [round((left + right) / 2.0) for left, right in zip(centers, centers[1:])]
        return [(0, splits[0]), (splits[0], splits[1]), (splits[1], splits[2]), (splits[2], w)]

    # T-pose horizontal arms can enter the neighboring view's empty gutter. Detect
    # the four body centers from the lower half, where arms cannot merge subjects,
    # then split at center midpoints while preserving all horizontal arm pixels.
    if len(runs) == 4:
        return runs
    lower_runs = active_runs(alpha[round(h * 0.43) :], minimum_width=80)
    if len(lower_runs) != 4:
        raise RuntimeError(f"T-pose expected four lower-body spans; detected {lower_runs}")
    centers = [(start + end) / 2.0 for start, end in lower_runs]
    split_1 = round((centers[0] + centers[1]) / 2.0)
    split_2 = round((centers[1] + centers[2]) / 2.0)
    split_3 = round((centers[2] + centers[3]) / 2.0)
    ranges = [(0, split_1), (split_1, split_2), (split_2, split_3), (split_3, w)]
    if any(end - start < 40 for start, end in ranges):
        raise RuntimeError(f"Invalid T-pose split ranges: {ranges}")
    return ranges


def subject_bbox(alpha: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.where(alpha >= 48)
    if not len(xs):
        raise RuntimeError("No foreground pixels in view crop")
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def normalize_profile_depth(
    prepared_images: list[Image.Image], views: list[dict], pose_dir: Path, pose: str
) -> dict:
    """Register character-left/right depth to their mean with a minimal x-only scale.

    Image generation can drift a nominally identical side envelope by a few pixels. The
    modeling contract caps that drift at three percent, so both exact profiles are
    mechanically registered to the same mean width while height and vertical placement
    remain unchanged. The correction is intentionally symmetric and recorded.
    """

    profile_indices = (1, 3)
    boxes: dict[int, tuple[int, int, int, int]] = {}
    for index in profile_indices:
        rgb = np.asarray(prepared_images[index], dtype=np.float32)
        difference = rgb - BACKGROUND.astype(np.float32)
        distance = np.sqrt(np.sum(difference * difference, axis=2))
        boxes[index] = subject_bbox((distance > 18.0).astype(np.uint8) * 255)
    source_widths = [boxes[index][2] - boxes[index][0] for index in profile_indices]
    target_width = round(sum(source_widths) / len(source_widths))
    corrections: list[dict] = []

    for index in profile_indices:
        x0, y0, x1, y1 = boxes[index]
        source_width = x1 - x0
        cutout = prepared_images[index].crop((x0, y0, x1, y1))
        cutout = cutout.resize((target_width, y1 - y0), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (CANVAS_SIZE, CANVAS_SIZE), tuple(BACKGROUND))
        offset = ((CANVAS_SIZE - target_width) // 2, y0)
        canvas.paste(cutout, offset)
        output = pose_dir / f"chr_npc_mira_{pose}_{VIEW_NAMES[index]}.png"
        canvas.save(output, optimize=True)
        prepared_images[index] = canvas
        views[index]["canvas_offset"] = list(offset)
        views[index]["scaled_subject_size"] = [target_width, y1 - y0]
        views[index]["sha256"] = sha256(output)
        corrections.append(
            {
                "view": VIEW_NAMES[index],
                "source_width": source_width,
                "target_width": target_width,
                "x_scale_ratio": target_width / source_width,
            }
        )

    return {
        "method": "symmetric mean-width x-only registration of exact profiles",
        "target_width_px": target_width,
        "corrections": corrections,
    }


def normalize_subject_heights(
    prepared_images: list[Image.Image], views: list[dict], pose_dir: Path, pose: str
) -> dict:
    """Normalize the actual keyed subject bbox to TARGET_HEIGHT in every view."""

    corrections: list[dict] = []
    for index, image in enumerate(prepared_images):
        rgb = np.asarray(image, dtype=np.float32)
        difference = rgb - BACKGROUND.astype(np.float32)
        distance = np.sqrt(np.sum(difference * difference, axis=2))
        x0, y0, x1, y1 = subject_bbox((distance > 18.0).astype(np.uint8) * 255)
        source_width, source_height = x1 - x0, y1 - y0
        scale = TARGET_HEIGHT / source_height
        target_width = round(source_width * scale)
        cutout = image.crop((x0, y0, x1, y1)).resize(
            (target_width, TARGET_HEIGHT), Image.Resampling.LANCZOS
        )
        canvas = Image.new("RGB", (CANVAS_SIZE, CANVAS_SIZE), tuple(BACKGROUND))
        offset = ((CANVAS_SIZE - target_width) // 2, (CANVAS_SIZE - TARGET_HEIGHT) // 2)
        canvas.paste(cutout, offset)
        output = pose_dir / f"chr_npc_mira_{pose}_{VIEW_NAMES[index]}.png"
        canvas.save(output, optimize=True)
        prepared_images[index] = canvas
        views[index]["canvas_offset"] = list(offset)
        views[index]["scaled_subject_size"] = [target_width, TARGET_HEIGHT]
        views[index]["sha256"] = sha256(output)
        corrections.append(
            {
                "view": VIEW_NAMES[index],
                "source_height": source_height,
                "target_height": TARGET_HEIGHT,
                "uniform_scale_ratio": scale,
            }
        )
    return {
        "method": "uniform scale from actual keyed subject bbox",
        "target_height_px": TARGET_HEIGHT,
        "corrections": corrections,
    }


def prepare_sheet(source: Path, out_dir: Path, pose: str) -> dict:
    image = Image.open(source).convert("RGB")
    rgb = np.asarray(image)
    estimated_background = estimate_background(rgb)
    alpha = foreground_alpha(rgb, estimated_background)
    ranges = pose_ranges(alpha, pose)
    pose_dir = out_dir / pose
    pose_dir.mkdir(parents=True, exist_ok=True)

    views: list[dict] = []
    prepared_images: list[Image.Image] = []
    for index, (name, (x0, x1)) in enumerate(zip(VIEW_NAMES, ranges)):
        local_rgb = rgb[:, x0:x1]
        local_alpha = alpha[:, x0:x1]
        bx0, by0, bx1, by1 = subject_bbox(local_alpha)
        pad = 4
        bx0, by0 = max(0, bx0 - pad), max(0, by0 - pad)
        bx1, by1 = min(local_rgb.shape[1], bx1 + pad), min(local_rgb.shape[0], by1 + pad)
        cutout = Image.fromarray(
            np.dstack((local_rgb[by0:by1, bx0:bx1], local_alpha[by0:by1, bx0:bx1])),
            "RGBA",
        )
        scale = min(TARGET_HEIGHT / cutout.height, 1000 / cutout.width)
        size = (max(1, round(cutout.width * scale)), max(1, round(cutout.height * scale)))
        cutout = cutout.resize(size, Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), tuple(BACKGROUND) + (255,))
        offset = ((CANVAS_SIZE - size[0]) // 2, (CANVAS_SIZE - size[1]) // 2)
        canvas.alpha_composite(cutout, offset)
        output = pose_dir / f"chr_npc_mira_{pose}_{name}.png"
        canvas.convert("RGB").save(output, optimize=True)
        prepared_images.append(canvas.convert("RGB"))
        views.append(
            {
                "index": index,
                "name": name,
                "source_x_range": [x0, x1],
                "source_subject_bbox": [x0 + bx0, by0, bx1 - bx0, by1 - by0],
                "canvas_size": [CANVAS_SIZE, CANVAS_SIZE],
                "canvas_offset": list(offset),
                "scaled_subject_size": list(size),
                "output": str(output.relative_to(out_dir)),
                "sha256": sha256(output),
            }
        )

    subject_height_registration = normalize_subject_heights(prepared_images, views, pose_dir, pose)
    profile_depth_registration = normalize_profile_depth(prepared_images, views, pose_dir, pose)

    contact_width = CANVAS_SIZE * 4
    contact = Image.new("RGB", (contact_width, CANVAS_SIZE), tuple(BACKGROUND))
    for index, view in enumerate(prepared_images):
        contact.paste(view, (index * CANVAS_SIZE, 0))
    contact_path = out_dir / f"chr_npc_mira_{pose}_turnaround.png"
    contact.save(contact_path, optimize=True)

    heights = [entry["scaled_subject_size"][1] for entry in views]
    source_heights = [entry["source_subject_bbox"][3] for entry in views]
    report = {
        "schema": "mira_modeling_views.v1",
        "pose": pose,
        "source": str(source.relative_to(out_dir)),
        "source_sha256": sha256(source),
        "source_size": list(image.size),
        "estimated_background_rgb": [round(float(value), 2) for value in estimated_background],
        "output_background_rgb": list(map(int, BACKGROUND)),
        "view_order": list(VIEW_NAMES),
        "views": views,
        "contact_sheet": str(contact_path.relative_to(out_dir)),
        "contact_sheet_sha256": sha256(contact_path),
        "source_height_error_percent": (max(source_heights) - min(source_heights)) / max(source_heights) * 100.0,
        "prepared_height_error_percent": (max(heights) - min(heights)) / max(heights) * 100.0,
        "subject_height_registration": subject_height_registration,
        "profile_depth_registration": profile_depth_registration,
        "drawn_ground_line": False,
    }
    report_path = pose_dir / "registration_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant-dir", required=True, type=Path)
    parser.add_argument("--a-source", required=True, type=Path)
    parser.add_argument("--t-source", required=True, type=Path)
    args = parser.parse_args()
    variant = args.variant_dir.resolve()
    reports = {
        "a_pose": prepare_sheet(args.a_source.resolve(), variant, "a_pose"),
        "t_pose": prepare_sheet(args.t_source.resolve(), variant, "t_pose"),
    }
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
