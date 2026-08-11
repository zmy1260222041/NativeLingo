"""Prepare clean, registered Rodin multi-view inputs from an approved turnaround.

The source sheet stays immutable.  Each view is cropped from an explicit seed range,
background-keyed to RGBA, kept at the sheet's shared vertical scale, and centered on
a 512x1024 transparent canvas.  This prevents adjacent characters and the ground
line from becoming unintended Rodin geometry.
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


def remove_ground_line(alpha: np.ndarray, rgb: np.ndarray, center_y: int, radius: int) -> None:
    """Remove only long near-black runs around the authored ground line."""
    height, width = alpha.shape
    for y in range(max(0, center_y - radius), min(height, center_y + radius + 1)):
        # Include the antialiased grey shoulders of the line, not only its black core.
        # The run-length gate keeps short foot/ink contours intact.
        dark = np.max(rgb[y], axis=1) < 210
        start = None
        for x in range(width + 1):
            active = x < width and bool(dark[x])
            if active and start is None:
                start = x
            elif not active and start is not None:
                if x - start >= 28:
                    alpha[y, start:x] = 0
                start = None


def prepare(config_path: Path) -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8"))
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
    remove_ground_line(
        alpha,
        rgb,
        int(config["ground_line_y"]),
        int(config.get("ground_line_radius", 3)),
    )

    canvas_width = int(config.get("canvas_width", 512))
    canvas_height = int(config.get("canvas_height", 1024))
    scale = canvas_height / image.height
    reports = []
    contact = Image.new("RGBA", (canvas_width * 4, canvas_height), (244, 236, 231, 255))
    draw = ImageDraw.Draw(contact)

    for index, (name, x_range) in enumerate(zip(VIEW_NAMES, config["view_x_ranges"])):
        x0, x1 = map(int, x_range)
        local_alpha = alpha[:, x0:x1]
        ys, xs = np.nonzero(local_alpha > 24)
        if len(xs) == 0:
            raise RuntimeError(f"No subject pixels found for {name} in x range {x_range}")
        pad = int(config.get("horizontal_padding_px", 12))
        subject_x0 = max(x0, x0 + int(xs.min()) - pad)
        subject_x1 = min(x1, x0 + int(xs.max()) + 1 + pad)

        crop_rgb = np.asarray(image)[:, subject_x0:subject_x1]
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
            }
        )

    contact_path = output_dir / "figure_contact_sheet.png"
    contact.convert("RGB").save(contact_path)
    report = {
        "schema": "rodin_reference_preparation.v2",
        "asset_id": config["asset_id"],
        "source": str(source.relative_to(config_path.parent)),
        "source_sha256": sha256(source),
        "source_size": list(image.size),
        "estimated_background_rgb": [round(float(value), 2) for value in background],
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
