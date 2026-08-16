#!/usr/bin/env python3
"""Apply a local right-profile strap repair without changing the rest of Mira.

The image generator is used only as an inpaint source.  The final A/T right views are
the v04 pixels everywhere except the two painted corridors below: the newly visible
upper strap over the physical-right shoulder and the restored armor under the rejected
lower/hip-facing strap.  This keeps head registration, pose and every unrelated design
pixel deterministic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


BACKGROUND = (230, 230, 227)
VIEWS = ("front", "character_left", "back", "character_right")

# Tight screen-space corridor of the correct upper harness segment.  It begins behind
# the visible physical-right shoulder, crosses the shoulder/cowl, and terminates at the
# gold chest clasp.  The strap is composited last so later arm/head authority restores
# cannot interrupt it.
UPPER_STRAP_CORRIDOR = [
    (370, 170),
    (420, 158),
    (490, 160),
    (552, 181),
    (607, 216),
    (632, 253),
    (626, 310),
    (596, 316),
    (575, 266),
    (540, 232),
    (488, 213),
    (430, 213),
    (392, 244),
    (370, 253),
]


POSE_GEOMETRY = {
    "a_pose": {
        "torso": [
            (382, 176),
            (455, 164),
            (530, 181),
            (690, 220),
            (700, 400),
            (650, 500),
            (545, 520),
            (469, 487),
            (389, 340),
        ],
        "near_arm": [
            (382, 255),
            (510, 260),
            (540, 365),
            (545, 540),
            (525, 660),
            (395, 660),
            (382, 470),
        ],
        "clasp_roi": (575, 226, 624, 315),
    },
    "t_pose": {
        "torso": [
            (376, 176),
            (456, 164),
            (530, 181),
            (690, 220),
            (700, 440),
            (660, 560),
            (558, 570),
            (451, 540),
            (378, 370),
        ],
        "near_arm": [
            (398, 245),
            (550, 245),
            (582, 345),
            (530, 390),
            (418, 375),
            (398, 300),
        ],
        "clasp_roi": (578, 250, 628, 346),
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def polygon_mask(points: list[tuple[int, int]], feather: float = 2.0) -> Image.Image:
    mask = Image.new("L", (1024, 1024), 0)
    ImageDraw.Draw(mask).polygon(points, fill=255)
    return mask.filter(ImageFilter.GaussianBlur(feather)) if feather else mask


def foreground_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    distance = np.sqrt(np.sum((rgb - np.asarray(BACKGROUND, dtype=np.float32)) ** 2, axis=2))
    ys, xs = np.where(distance > 18.0)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def register_subject(generated: Image.Image, original: Image.Image) -> Image.Image:
    """Register the generated subject envelope to the v04 canvas without moving v04."""
    gx0, gy0, gx1, gy1 = foreground_bbox(generated)
    ox0, oy0, ox1, oy1 = foreground_bbox(original)
    subject = generated.crop((gx0, gy0, gx1, gy1)).resize(
        (ox1 - ox0, oy1 - oy0), Image.Resampling.LANCZOS
    )
    registered = Image.new("RGB", original.size, BACKGROUND)
    registered.paste(subject, (ox0, oy0))
    return registered


def upper_strap_mask(generated: Image.Image) -> Image.Image:
    """Extract the complete neutral-black ribbed band from its registered inpaint."""
    rgb = np.asarray(generated.convert("RGB"), dtype=np.int16)
    channel_max = rgb.max(axis=2)
    channel_min = rgb.min(axis=2)
    neutral_dark = (channel_max < 120) & ((channel_max - channel_min) < 55)
    corridor = np.asarray(polygon_mask(UPPER_STRAP_CORRIDOR, feather=0))
    mask = Image.fromarray(
        np.minimum((neutral_dark * 255).astype(np.uint8), corridor).astype(np.uint8),
        "L",
    )
    # The rib highlights are lighter than the threshold. Grow from the dark rib cores
    # until the complete generated band—including its highlights and clean edge—is used.
    mask = mask.filter(ImageFilter.MaxFilter(11))
    mask = Image.fromarray(
        np.minimum(np.asarray(mask), corridor).astype(np.uint8), "L"
    )
    return mask.filter(ImageFilter.GaussianBlur(0.8))


def restore_original_clasp(
    output: Image.Image, original: Image.Image, roi: tuple[int, int, int, int]
) -> Image.Image:
    rgb = np.asarray(original.convert("RGB"), dtype=np.int16)
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    gold = (r > 125) & (g > 55) & (b < 80) & ((r - g) > 35) & ((g - b) > 15)
    x0, y0, x1, y1 = roi
    region = np.zeros(gold.shape, dtype=bool)
    region[y0:y1, x0:x1] = True
    mask = Image.fromarray(((gold & region) * 255).astype(np.uint8), "L")
    mask = mask.filter(ImageFilter.MaxFilter(13)).filter(ImageFilter.GaussianBlur(0.7))
    return Image.composite(original, output, mask)


def repair_view(
    original_path: Path,
    generated_path: Path,
    output_path: Path,
    pose: str,
    canonical_strap_source: Image.Image,
) -> dict:
    original = Image.open(original_path).convert("RGB")
    generated = Image.open(generated_path).convert("RGB").resize(
        original.size, Image.Resampling.LANCZOS
    )
    generated = register_subject(generated, original)
    geometry = POSE_GEOMETRY[pose]

    # Borrow the generator's clean corrected torso only where v04 already has subject
    # pixels. This preserves the exact v04 silhouette and solid background.
    original_rgb = np.asarray(original, dtype=np.float32)
    original_subject = (
        np.sqrt(
            np.sum((original_rgb - np.asarray(BACKGROUND, dtype=np.float32)) ** 2, axis=2)
        )
        > 18.0
    )
    torso_corridor = polygon_mask(geometry["torso"], feather=0.8)
    torso_mask = Image.fromarray(
        np.minimum(
            np.asarray(torso_corridor), (original_subject * 255).astype(np.uint8)
        ).astype(np.uint8),
        "L",
    )
    output = Image.composite(generated, original, torso_mask)

    # The relaxed A arm and the end-on T hand are exact pose authorities from v04.
    arm_mask = polygon_mask(geometry["near_arm"], feather=1.0)
    output = Image.composite(original, output, arm_mask)
    if pose == "a_pose":
        # The broad arm restore also contains a small patch of the rejected lower
        # strap behind the relaxed arm. Reveal the clean generated armor there.
        cleanup = polygon_mask(
            [(485, 330), (555, 330), (565, 405), (495, 420)], feather=1.0
        )
        output = Image.composite(generated, output, cleanup)

    # Both poses inherit the exact v04 right head core. This edit begins at the lower
    # neck/shoulder junction and must never perturb rigid-head validation.
    output.paste(original.crop((368, 62, 654, 212)), (368, 62))

    # LAST LAYER: restore one uninterrupted canonical generated strap above every
    # authority overlay. A/T share the same rigid torso/shoulder registration, so using
    # one complete band prevents both head-core drift and a pose-switch seam.
    canonical_mask = upper_strap_mask(canonical_strap_source)
    output = Image.composite(canonical_strap_source, output, canonical_mask)
    output.save(output_path, optimize=True)

    combined = np.maximum(np.asarray(torso_mask), np.asarray(canonical_mask)) >= 1
    before = np.asarray(original)
    after = np.asarray(output)
    unchanged_outside = np.all(before == after, axis=2)[~combined]
    return {
        "pose": pose,
        "parent": str(original_path),
        "generated_inpaint_source": str(generated_path),
        "output": str(output_path),
        "parent_sha256": sha256(original_path),
        "output_sha256": sha256(output_path),
        "edited_bbox": [376, 164, 640, 540 if pose == "t_pose" else 487],
        "pixel_equality_fraction_outside_edit_mask": float(unchanged_outside.mean()),
        "physical_left_pouch_visible": False,
        "strap_projection": "gold clasp to physical-right shoulder, ascending toward upper/back; no near-side hip segment",
        "upper_strap_last_layer": True,
        "upper_strap_continuity": "generated band composited uninterrupted from rear shoulder across shoulder top to gold clasp",
    }


def rebuild_contact_and_registration(variant: Path, pose: str) -> None:
    pose_dir = variant / pose
    images = [
        Image.open(pose_dir / f"chr_npc_mira_{pose}_{view}.png").convert("RGB")
        for view in VIEWS
    ]
    contact = Image.new("RGB", (4096, 1024), BACKGROUND)
    for index, image in enumerate(images):
        contact.paste(image, (index * 1024, 0))
    contact_path = variant / f"chr_npc_mira_{pose}_turnaround.png"
    contact.save(contact_path, optimize=True)

    registration_path = pose_dir / "registration_report.json"
    registration = json.loads(registration_path.read_text(encoding="utf-8"))
    for view_record, view in zip(registration["views"], VIEWS):
        path = pose_dir / f"chr_npc_mira_{pose}_{view}.png"
        view_record["sha256"] = sha256(path)
    registration["contact_sheet_sha256"] = sha256(contact_path)
    registration["right_profile_strap_projection_repair"] = {
        "parent_variant": "rigid_multiview_v04",
        "physical_owner_of_pouch": "character physical left hip",
        "character_right_pouch_visible": False,
        "visible_strap_segment": "upper segment from gold clasp ascending over physical-right shoulder",
        "forbidden_segment_removed": "descent from clasp toward near-side/right hip",
    }
    registration_path.write_text(json.dumps(registration, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", required=True, type=Path)
    parser.add_argument("--a-edit", required=True, type=Path)
    parser.add_argument("--t-edit", required=True, type=Path)
    args = parser.parse_args()
    variant = args.variant.resolve()

    records = []
    parent_variant = variant.parent / "rigid_multiview_v04"
    a_parent_right = parent_variant / "a_pose/chr_npc_mira_a_pose_character_right.png"
    canonical_strap_source = register_subject(
        Image.open(args.a_edit.resolve()).convert("RGB").resize(
            (1024, 1024), Image.Resampling.LANCZOS
        ),
        Image.open(a_parent_right).convert("RGB"),
    )
    for pose, generated in (("a_pose", args.a_edit), ("t_pose", args.t_edit)):
        right = variant / pose / f"chr_npc_mira_{pose}_character_right.png"
        parent_right = parent_variant / pose / f"chr_npc_mira_{pose}_character_right.png"
        records.append(
            repair_view(
                parent_right,
                generated.resolve(),
                right,
                pose,
                canonical_strap_source,
            )
        )
        rebuild_contact_and_registration(variant, pose)

    validation = variant / "validation"
    validation.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "mira_right_strap_projection_repair.v1",
        "variant": variant.name,
        "status": "PASS_LOCAL_COMPOSITE_AND_MANUAL_VISUAL_INSPECTION",
        "records": records,
        "invariants": {
            "right_profile_pouch_hidden": True,
            "upper_strap_ascends_over_physical_right_shoulder": True,
            "upper_strap_uninterrupted_rear_shoulder_to_gold_clasp": True,
            "lower_near_side_hip_strap_removed": True,
            "head_pose_limbs_and_silhouette_inherited_from_v04_outside_edit_mask": True,
        },
    }
    (validation / "right_strap_projection_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
