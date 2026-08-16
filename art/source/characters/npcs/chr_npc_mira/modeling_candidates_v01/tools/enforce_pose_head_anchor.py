#!/usr/bin/env python3
"""Make T-pose heads pixel-identical to accepted A-pose heads, view by view.

The A and T images have already been normalized to the same 1024 canvas and 900-pixel
subject height.  This script replaces only the top head band in each T view with the
corresponding accepted A view, retaining the T arms and body below the head.  It records
the operation and rebuilds the T contact sheet and registration hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


BACKGROUND = np.array((230, 230, 227), dtype=np.float32)
VIEW_NAMES = ("front", "character_left", "back", "character_right")
HEAD_CORE_HEIGHT = 150
HEAD_BLEND_HEIGHT = 30


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def foreground_mask(image: Image.Image) -> np.ndarray:
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    delta = rgb - BACKGROUND
    return np.sqrt(np.sum(delta * delta, axis=2)) > 18.0


def top(mask: np.ndarray) -> int:
    ys = np.where(mask)[0]
    if not len(ys):
        raise RuntimeError("No foreground found")
    return int(ys.min())


def replace_head(a_image: Image.Image, t_image: Image.Image) -> tuple[Image.Image, dict]:
    a_image = a_image.convert("RGB")
    t_image = t_image.convert("RGB")
    a_mask = foreground_mask(a_image)
    t_mask = foreground_mask(t_image)
    a_top = top(a_mask)
    t_top = top(t_mask)
    # Find the head's horizontal envelope before shoulders/arms enter the frame.
    head_probe_end = min(a_image.height, a_top + 105)
    probe_y, probe_x = np.where(a_mask[a_top:head_probe_end])
    t_probe_end = min(t_image.height, t_top + 105)
    t_probe_y, t_probe_x = np.where(t_mask[t_top:t_probe_end])
    if not len(probe_x) or not len(t_probe_x):
        raise RuntimeError("No head foreground found")
    # Cover the union of A and generated-T head envelopes. Pixels outside the A head but
    # inside the old T envelope are replaced by A's exact background, preventing ghosts.
    x0 = max(0, min(int(probe_x.min()), int(t_probe_x.min())) - 36)
    x1 = min(a_image.width, max(int(probe_x.max()), int(t_probe_x.max())) + 37)
    y0 = min(a_top, t_top)
    core_end = min(a_image.height, y0 + HEAD_CORE_HEIGHT)
    blend_end = min(a_image.height, core_end + HEAD_BLEND_HEIGHT)

    # Blend the entire head rectangle instead of cutting foreground masks at a hard row.
    # The canonical A image fully owns the head core; a smooth vertical fade across the
    # unchanged neck/shoulder junction prevents a horizontal compositing seam.
    source = np.asarray(a_image, dtype=np.float32)
    target = np.asarray(t_image, dtype=np.float32)
    alpha = np.zeros(a_mask.shape, dtype=np.float32)
    alpha[y0:core_end, x0:x1] = 1.0
    if blend_end > core_end:
        fade = np.linspace(1.0, 0.0, blend_end - core_end, endpoint=False, dtype=np.float32)
        alpha[core_end:blend_end, x0:x1] = fade[:, None]
    # The union rectangle reaches only into uniform background at its side edges, so no
    # lateral feather is necessary; exact A background cleanly erases the old T envelope.
    out = source * alpha[:, :, None] + target * (1.0 - alpha[:, :, None])
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB"), {
        "a_top": a_top,
        "t_top_before": t_top,
        "head_roi": [x0, y0, x1, blend_end],
        "core_height": HEAD_CORE_HEIGHT,
        "blend_height": HEAD_BLEND_HEIGHT,
        "fully_canonical_pixels": int((alpha == 1.0).sum()),
        "blended_pixels": int(((alpha > 0.0) & (alpha < 1.0)).sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", required=True, type=Path)
    args = parser.parse_args()
    variant = args.variant.resolve()
    records = []
    prepared = []
    for view in VIEW_NAMES:
        a_path = variant / "a_pose" / f"chr_npc_mira_a_pose_{view}.png"
        t_path = variant / "t_pose" / f"chr_npc_mira_t_pose_{view}.png"
        output, record = replace_head(Image.open(a_path), Image.open(t_path))
        output.save(t_path, optimize=True)
        prepared.append(output)
        record.update(
            {
                "view": view,
                "a_source": str(a_path.relative_to(variant)),
                "t_output": str(t_path.relative_to(variant)),
                "t_output_sha256": sha256(t_path),
            }
        )
        records.append(record)

    contact = Image.new("RGB", (4096, 1024), tuple(BACKGROUND.astype(np.uint8)))
    for index, image in enumerate(prepared):
        contact.paste(image, (index * 1024, 0))
    contact_path = variant / "chr_npc_mira_t_pose_turnaround.png"
    contact.save(contact_path, optimize=True)

    registration_path = variant / "t_pose" / "registration_report.json"
    registration = json.loads(registration_path.read_text(encoding="utf-8"))
    for view_record, output_record in zip(registration["views"], records):
        view_record["sha256"] = output_record["t_output_sha256"]
    registration["contact_sheet_sha256"] = sha256(contact_path)
    registration["cross_pose_head_anchor"] = {
        "method": "pixel-identical A-pose head core with soft neck/shoulder transition",
        "canonical_pose": "a_pose",
        "records": records,
    }
    registration_path.write_text(json.dumps(registration, indent=2), encoding="utf-8")
    print(json.dumps(registration["cross_pose_head_anchor"], indent=2))


if __name__ == "__main__":
    main()
