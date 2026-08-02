#!/usr/bin/env python3
"""Render gallery detections into indoor/outdoor contact sheets for review."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

PANEL = (640, 430)
GRID = (2, 5)
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def _font(size: int):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except OSError:
        return ImageFont.load_default()


def _panel(gallery: Path, result: dict) -> Image.Image:
    with Image.open(gallery / result["file"]) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    source_width, source_height = image.size
    scale = min(PANEL[0] / source_width, (PANEL[1] - 30) / source_height)
    resized = image.resize(
        (round(source_width * scale), round(source_height * scale)),
        Image.Resampling.LANCZOS,
    )
    panel = Image.new("RGB", PANEL, "#15181e")
    offset_x = (PANEL[0] - resized.width) // 2
    offset_y = 30 + (PANEL[1] - 30 - resized.height) // 2
    detection_width, detection_height = result.get(
        "size", [source_width, source_height]
    )
    box_scale_x = resized.width / detection_width
    box_scale_y = resized.height / detection_height
    panel.paste(resized, (offset_x, offset_y))
    draw = ImageDraw.Draw(panel)
    draw.text((8, 5), result["file"], fill="white", font=_font(17))

    for item in result["objects"]:
        x, y, width, height = item["box"]
        box = (
            offset_x + x * box_scale_x,
            offset_y + y * box_scale_y,
            offset_x + (x + width) * box_scale_x,
            offset_y + (y + height) * box_scale_y,
        )
        draw.rectangle(box, outline="#55e000", width=3)
        label = f'{item["label_en"]} {item["score"]:.2f}'
        text_box = draw.textbbox((box[0], box[1]), label, font=_font(16))
        text_width = text_box[2] - text_box[0] + 8
        text_height = text_box[3] - text_box[1] + 6
        label_top = max(offset_y, box[1] - text_height)
        draw.rectangle(
            (box[0], label_top, box[0] + text_width, label_top + text_height),
            fill="#297400",
        )
        draw.text(
            (box[0] + 4, label_top + 2),
            label,
            fill="white",
            font=_font(16),
        )
    return panel


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gallery", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    payload = json.loads(args.baseline.read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for scene in ("indoor", "outdoor"):
        scene_rows = [
            result
            for result in payload["results"]
            if result["file"].startswith(f"{scene}/")
        ]
        page_size = GRID[0] * GRID[1]
        pages = [
            scene_rows[index:index + page_size]
            for index in range(0, len(scene_rows), page_size)
        ]
        for page_index, rows in enumerate(pages, start=1):
            sheet = Image.new(
                "RGB",
                (PANEL[0] * GRID[0], PANEL[1] * GRID[1]),
                "#0d0f13",
            )
            for index, result in enumerate(rows):
                x = index % GRID[0] * PANEL[0]
                y = index // GRID[0] * PANEL[1]
                sheet.paste(_panel(args.gallery, result), (x, y))
            suffix = "" if len(pages) == 1 else f"-{page_index:02d}"
            output = (
                args.output_dir / f"{scene}-yoloe-filtered{suffix}.jpg"
            )
            sheet.save(output, quality=92)
            print(output)


if __name__ == "__main__":
    main()
