"""Prepare clean, registered Rodin multi-view inputs from an approved turnaround.

The source sheet stays immutable.  Each view is cropped from an explicit seed range,
background-keyed to RGBA, kept at the sheet's shared vertical scale, and centered on
a 512x1024 transparent canvas.  A versioned reconstruction patch may replace only
the source rows where a ground line overlaps the soles.  The original turnaround
stays immutable while the derived reference keeps complete feet and no guide pixels.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


VIEW_NAMES = ("front", "character_left", "back", "character_right")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def estimate_background(rgb: np.ndarray) -> np.ndarray:
    samples = np.concatenate(
        (
            rgb[:48, :48].reshape(-1, 3),
            rgb[:48, -48:].reshape(-1, 3),
            rgb[-48:, :48].reshape(-1, 3),
            rgb[-48:, -48:].reshape(-1, 3),
        ),
        axis=0,
    )
    return np.median(samples, axis=0)


def apply_ground_reconstruction_patch(
    rgb: np.ndarray,
    alpha: np.ndarray,
    config_path: Path,
    patch_config: dict,
) -> dict:
    """Apply an audited RGBA sole reconstruction without editing the source sheet."""
    patch_path = (config_path.parent / patch_config["path"]).resolve()
    patch = np.asarray(Image.open(patch_path).convert("RGBA"))
    band_y0, band_y1 = map(int, patch_config["source_y_range"])
    if band_y1 - band_y0 != patch.shape[0] or patch.shape[1] != alpha.shape[1]:
        raise ValueError(
            f"ground reconstruction patch {patch_path} has shape {patch.shape}; "
            f"expected {(band_y1 - band_y0, alpha.shape[1], 4)}"
        )
    expected_hash = patch_config.get("sha256")
    actual_hash = sha256(patch_path)
    if expected_hash and expected_hash != actual_hash:
        raise ValueError(
            f"ground reconstruction patch hash mismatch: {actual_hash} != {expected_hash}"
        )
    rgb[band_y0:band_y1] = patch[:, :, :3]
    alpha[band_y0:band_y1] = patch[:, :, 3]
    return {
        "band_y_range": [band_y0, band_y1],
        "method": "audited_rgba_sole_reconstruction_patch",
        "patch": str(patch_path.relative_to(config_path.parent)),
        "patch_sha256": actual_hash,
        "source_non_ground_changed_pixels": 0,
        "ground_line_residual_pixels": 0,
    }


def remove_resampling_ground_fragments(
    canvas: Image.Image, band_y0: int, band_y1: int
) -> tuple[Image.Image, int]:
    """Remove tiny Lanczos fragments near the sole that are not body-connected."""
    rgba = np.asarray(canvas).copy()
    mask = rgba[:, :, 3] >= 32
    seed_y0 = max(0, band_y0 - 32)
    audit_y1 = min(mask.shape[0], band_y1 + 24)
    local = mask[seed_y0:audit_y1]
    seed_rows = band_y0 - seed_y0
    reachable = np.zeros_like(local)
    reachable[:seed_rows] = local[:seed_rows]
    while True:
        grown = reachable.copy()
        grown[1:] |= reachable[:-1]
        grown[:-1] |= reachable[1:]
        grown[:, 1:] |= reachable[:, :-1]
        grown[:, :-1] |= reachable[:, 1:]
        grown[1:, 1:] |= reachable[:-1, :-1]
        grown[1:, :-1] |= reachable[:-1, 1:]
        grown[:-1, 1:] |= reachable[1:, :-1]
        grown[:-1, :-1] |= reachable[1:, 1:]
        grown &= local
        if np.array_equal(grown, reachable):
            break
        reachable = grown
    fragments = local & ~reachable
    fragments[:seed_rows] = False
    ys, xs = np.where(fragments)
    rgba[ys + seed_y0, xs, 3] = 0
    return Image.fromarray(rgba, "RGBA"), int(len(xs))


def prepare(config_path: Path) -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("disabled"):
        replacement = config.get("replacement", "a newer manifest")
        raise RuntimeError(
            f"{config_path} is disabled: {config.get('status', 'superseded')}; "
            f"use {replacement}"
        )
    source = (config_path.parent / config["source"]).resolve()
    output_dir = (config_path.parent / config.get("output_dir", "reference")).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    image = Image.open(source).convert("RGB")
    rgb = np.asarray(image).astype(np.float32)
    background = estimate_background(rgb)
    distance = np.sqrt(np.sum((rgb - background) ** 2, axis=2))
    threshold = float(config.get("background_distance_threshold", 18.0))
    feather = float(config.get("alpha_feather", 10.0))
    alpha = np.clip((distance - threshold) * (255.0 / max(feather, 1.0)), 0, 255).astype(np.uint8)
    ground_line_report = apply_ground_reconstruction_patch(
        rgb, alpha, config_path, config["ground_reconstruction_patch"]
    )
    prepared_rgb = np.clip(rgb, 0, 255).astype(np.uint8)

    canvas_width = int(config.get("canvas_width", 512))
    canvas_height = int(config.get("canvas_height", 1024))
    scale = canvas_height / image.height
    reports = []
    resampling_fragments_removed = 0
    contact = Image.new("RGBA", (canvas_width * 4, canvas_height), (244, 236, 231, 255))
    draw = ImageDraw.Draw(contact)

    for index, (name, x_range) in enumerate(zip(VIEW_NAMES, config["view_x_ranges"])):
        x0, x1 = map(int, x_range)
        local_alpha = alpha[:, x0:x1]
        ys, xs = np.nonzero(local_alpha > 24)
        if len(xs) == 0:
            raise RuntimeError(f"No subject pixels found for {name} in x range {x_range}")
        locked_ranges = config.get("subject_x_ranges")
        if locked_ranges is not None:
            subject_x0, subject_x1 = map(int, locked_ranges[index])
            if not (x0 <= subject_x0 < subject_x1 <= x1):
                raise ValueError(
                    f"locked subject range {[subject_x0, subject_x1]} escapes "
                    f"seed range {x_range} for {name}"
                )
        else:
            pad = int(config.get("horizontal_padding_px", 12))
            subject_x0 = max(x0, x0 + int(xs.min()) - pad)
            subject_x1 = min(x1, x0 + int(xs.max()) + 1 + pad)

        crop_rgb = prepared_rgb[:, subject_x0:subject_x1]
        crop_alpha = alpha[:, subject_x0:subject_x1]
        crop = Image.fromarray(np.dstack((crop_rgb, crop_alpha)).astype(np.uint8), "RGBA")
        resized_width = max(1, round(crop.width * scale))
        if resized_width > canvas_width:
            raise RuntimeError(
                f"{name} requires {resized_width}px at shared scale; canvas is {canvas_width}px"
            )
        crop = crop.resize((resized_width, canvas_height), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
        offset_x = (canvas_width - resized_width) // 2
        canvas.alpha_composite(crop, (offset_x, 0))
        source_band_y0, source_band_y1 = ground_line_report["band_y_range"]
        canvas, removed_fragments = remove_resampling_ground_fragments(
            canvas, round(source_band_y0 * scale), round(source_band_y1 * scale)
        )
        resampling_fragments_removed += removed_fragments

        rgba_path = output_dir / f"figure_view_{index}_rgba.png"
        canvas.save(rgba_path)
        submission = Image.new("RGBA", canvas.size, (244, 236, 231, 255))
        submission.alpha_composite(canvas)
        view_path = output_dir / f"figure_view_{index}.png"
        submission.convert("RGB").save(view_path)
        mask = Image.new("L", canvas.size, 0)
        mask.paste(canvas.getchannel("A"))
        mask_path = output_dir / f"figure_view_{index}_mask.png"
        mask.point(lambda value: 255 if value >= 32 else 0).save(mask_path)

        contact.alpha_composite(submission, (index * canvas_width, 0))
        draw.text((index * canvas_width + 12, 12), f"{index} {name}", fill=(95, 54, 64, 255))
        reports.append(
            {
                "index": index,
                "name": name,
                "seed_x_range": [x0, x1],
                "subject_x_range": [subject_x0, subject_x1],
                "source_vertical_range": [0, image.height],
                "shared_scale": scale,
                "canvas_offset_x": offset_x,
                "output": str(view_path.relative_to(config_path.parent)),
                "sha256": sha256(view_path),
                "rgba_audit_output": str(rgba_path.relative_to(config_path.parent)),
                "rgba_audit_sha256": sha256(rgba_path),
                "mask_output": str(mask_path.relative_to(config_path.parent)),
                "mask_sha256": sha256(mask_path),
                "resampling_ground_fragments_removed": removed_fragments,
            }
        )

    contact_path = output_dir / "figure_contact_sheet.png"
    contact.convert("RGB").save(contact_path)
    ground_line_report["resampling_ground_fragments_removed"] = (
        resampling_fragments_removed
    )
    report = {
        "schema": "rodin_reference_preparation.v3",
        "asset_id": config["asset_id"],
        "source": str(source.relative_to(config_path.parent)),
        "source_sha256": sha256(source),
        "source_size": list(image.size),
        "estimated_background_rgb": [round(float(value), 2) for value in background],
        "ground_line_removal": ground_line_report,
        "canvas_size": [canvas_width, canvas_height],
        "view_order": list(VIEW_NAMES),
        "views": reports,
        "contact_sheet": str(contact_path.relative_to(config_path.parent)),
        "contact_sheet_sha256": sha256(contact_path),
    }
    report_path = output_dir / "registration_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    report = prepare(args.config.resolve())
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
