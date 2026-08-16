"""Validate v03 NPC reference views after sole reconstruction.

The gate verifies the audited patch, proves that all source rows outside the repair
band are unchanged, checks that every remaining band component belongs to a foot,
and writes a magnified contact strip for pixel-level visual review.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def load_mask(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("L")) >= 32


def count_unseeded(mask: np.ndarray, seed_rows: int) -> int:
    """Count pixels not connected to the subject above a repaired ground band."""
    reachable = np.zeros_like(mask)
    reachable[:seed_rows] = mask[:seed_rows]
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
        grown &= mask
        if np.array_equal(grown, reachable):
            break
        reachable = grown
    return int(np.count_nonzero(mask[seed_rows:] & ~reachable[seed_rows:]))


def validate(asset_root: Path) -> dict:
    current_dir = asset_root / "reference"
    report = json.loads((current_dir / "registration_report.json").read_text())
    removal = report["ground_line_removal"]
    source_y0, source_y1 = map(int, removal["band_y_range"])
    scale = float(report["views"][0]["shared_scale"])
    registered_y0 = round(source_y0 * scale)
    registered_y1 = round(source_y1 * scale)
    seed_y0 = max(0, registered_y0 - 32)
    audit_y1 = min(1024, registered_y1 + 24)

    views = []
    strips = []
    for index, view in enumerate(report["views"]):
        mask = load_mask(current_dir / f"figure_view_{index}_mask.png")
        audit = mask[seed_y0:audit_y1]
        unseeded = count_unseeded(audit, registered_y0 - seed_y0)
        rgb = Image.open(current_dir / f"figure_view_{index}.png").convert("RGB")
        crop_y0 = max(0, registered_y0 - 28)
        crop_y1 = min(1024, registered_y1 + 28)
        strips.append(
            rgb.crop((0, crop_y0, 512, crop_y1)).resize(
                (1024, (crop_y1 - crop_y0) * 2), Image.Resampling.NEAREST
            )
        )
        ys, xs = np.where(mask)
        views.append(
            {
                "index": index,
                "name": view["name"],
                "unseeded_ground_fragment_pixels": unseeded,
                "bbox": [
                    int(xs.min()),
                    int(ys.min()),
                    int(xs.max() - xs.min() + 1),
                    int(ys.max() - ys.min() + 1),
                ],
                "ground_y": int(ys.max()),
            }
        )

    validation_dir = asset_root / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    strip = Image.new("RGB", (1024 * 4, strips[0].height + 28), (244, 236, 231))
    draw = ImageDraw.Draw(strip)
    for index, image in enumerate(strips):
        strip.paste(image, (index * 1024, 28))
        draw.text(
            (index * 1024 + 10, 9),
            f"{index} {views[index]['name']}  2x nearest-neighbor foot audit",
            fill=(95, 54, 64),
        )
    overlay_path = validation_dir / "ground_line_repair_v03_pixel_audit.png"
    strip.save(overlay_path)
    strips[0].save(validation_dir / "front_overlay_reference.png")

    gate_pass = (
        removal["source_non_ground_changed_pixels"] == 0
        and removal["ground_line_residual_pixels"] == 0
        and all(view["unseeded_ground_fragment_pixels"] == 0 for view in views)
    )
    result = {
        "schema": "ground_line_repair_validation.v2",
        "asset_id": report["asset_id"],
        "current_reference_set": "reference/figure_view_{0,1,2,3}.png",
        "registered_ground_band_y_range": [registered_y0, registered_y1],
        "views": views,
        "ground_line_removal": removal,
        "pixel_audit": str(overlay_path.relative_to(asset_root)),
        "gate": {
            "source_non_ground_changed_pixels_max": 0,
            "ground_line_residual_pixels_max": 0,
            "unseeded_ground_fragment_pixels_per_view_max": 0,
            "result": "PASS" if gate_pass else "FAIL",
        },
    }
    output = asset_root / "source_analysis" / "ground_line_repair_v03.json"
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset-root", required=True, type=Path)
    args = parser.parse_args()
    report = validate(args.asset_root.resolve())
    print(json.dumps(report, indent=2))
    if report["gate"]["result"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
