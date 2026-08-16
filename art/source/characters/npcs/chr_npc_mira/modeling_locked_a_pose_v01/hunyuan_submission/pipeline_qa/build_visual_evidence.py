"""Create non-destructive, registered silhouette evidence for the A-pose Hunyuan review.

This does not alter the source PNGs or cloud GLB.  It only turns the already-rendered
orthographic clay previews into foreground masks, registers their height/center to the
approved view masks, and records the resulting silhouette comparison.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


OUT = Path(__file__).resolve().parent
SUBMISSION = OUT.parent
LOCK = SUBMISSION.parent
ANALYSIS = OUT / "source_analysis"
VALIDATION = OUT / "validation"

VIEWS = (
    ("front", "chr_npc_mira_a_pose_front.png", "mesh_neg_y_clay.png"),
    ("character_left", "chr_npc_mira_a_pose_character_left.png", "mesh_pos_x_clay.png"),
    ("back", "chr_npc_mira_a_pose_back.png", "mesh_pos_y_clay.png"),
    ("character_right", "chr_npc_mira_a_pose_character_right.png", "mesh_neg_x_clay.png"),
)


def bbox(mask: Image.Image) -> tuple[int, int, int, int]:
    b = mask.getbbox()
    if not b:
        raise RuntimeError("empty foreground mask")
    return b


def source_mask(image: Image.Image) -> Image.Image:
    # The approved, processed Hunyuan panels have exact #e6e6e3 backgrounds.
    src = image.convert("RGB")
    pix = src.load()
    result = Image.new("L", src.size)
    out = result.load()
    for y in range(src.height):
        for x in range(src.width):
            r, g, b = pix[x, y]
            out[x, y] = 255 if max(abs(r - 230), abs(g - 230), abs(b - 227)) > 18 else 0
    return result


def render_mask(image: Image.Image) -> Image.Image:
    # Workbench renders use a uniform dark background.  Treat only the material/cavity
    # light values as foreground; the corner is the authoritative background sample.
    src = image.convert("RGB")
    bg = src.getpixel((0, 0))
    pix = src.load()
    result = Image.new("L", src.size)
    out = result.load()
    for y in range(src.height):
        for x in range(src.width):
            r, g, b = pix[x, y]
            out[x, y] = 255 if max(abs(r - bg[0]), abs(g - bg[1]), abs(b - bg[2])) > 20 else 0
    return result


def register(model_mask: Image.Image, reference_mask: Image.Image) -> Image.Image:
    """Height-scale and center-align only; width remains a measured comparison signal."""
    mb = bbox(model_mask)
    rb = bbox(reference_mask)
    mh = mb[3] - mb[1]
    rh = rb[3] - rb[1]
    scale = rh / mh
    resized = model_mask.resize((round(model_mask.width * scale), round(model_mask.height * scale)), Image.Resampling.NEAREST)
    mb2 = bbox(resized)
    canvas = Image.new("L", reference_mask.size)
    ref_cx = (rb[0] + rb[2]) / 2
    ref_cy = (rb[1] + rb[3]) / 2
    mod_cx = (mb2[0] + mb2[2]) / 2
    mod_cy = (mb2[1] + mb2[3]) / 2
    canvas.paste(resized, (round(ref_cx - mod_cx), round(ref_cy - mod_cy)))
    return canvas


def iou(a: Image.Image, b: Image.Image) -> float:
    aa, bb = a.load(), b.load()
    inter = union = 0
    for y in range(a.height):
        for x in range(a.width):
            av, bv = aa[x, y] > 0, bb[x, y] > 0
            inter += av and bv
            union += av or bv
    return inter / union if union else 0.0


def overlay(reference: Image.Image, model: Image.Image) -> Image.Image:
    out = Image.new("RGB", reference.size, (20, 24, 31))
    rpx, mpx, opx = reference.load(), model.load(), out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, m = rpx[x, y] > 0, mpx[x, y] > 0
            if r and m:
                opx[x, y] = (246, 244, 222)   # matched
            elif r:
                opx[x, y] = (224, 88, 88)     # reference-only
            elif m:
                opx[x, y] = (74, 196, 214)    # model-only
    return out


def main() -> None:
    ANALYSIS.mkdir(parents=True, exist_ok=True)
    VALIDATION.mkdir(parents=True, exist_ok=True)
    results = []
    for name, source_name, render_name in VIEWS:
        source_path = LOCK / "hunyuan_input" / source_name
        render_path = SUBMISSION / "inspection" / render_name
        ref = source_mask(Image.open(source_path))
        raw_model = render_mask(Image.open(render_path))
        model = register(raw_model, ref)
        ref_box, raw_box, model_box = bbox(ref), bbox(raw_model), bbox(model)
        metric = {
            "view": name,
            "reference": str(source_path.relative_to(LOCK)),
            "render": str(render_path.relative_to(LOCK)),
            "reference_mask_bbox_xyxy": ref_box,
            "raw_model_mask_bbox_xyxy": raw_box,
            "registered_model_mask_bbox_xyxy": model_box,
            "height_registered": True,
            "normalized_silhouette_iou": round(iou(ref, model), 4),
            "interpretation": "Silhouette-only, after height/center registration; it does not validate hidden surfaces or exact material details.",
        }
        (ANALYSIS / f"{name}_silhouette.json").write_text(json.dumps(metric, indent=2) + "\n", encoding="utf-8")
        results.append(metric)
        if name == "front":
            ref.save(VALIDATION / "front_reference_mask.png")
            model.save(VALIDATION / "front_model_mask_registered.png")
            overlay(ref, model).save(VALIDATION / "front_overlay_reference.png")
    report = {
        "schema": "mira_a_pose_hunyuan_visual_registration.v1",
        "reference_lock": "A_POSE_ONLY_MODELING_LOCK",
        "views": results,
        "thresholds": {
            "first_pass_humanoid_silhouette_iou": 0.82,
            "hard_part_constraints": "manual review required",
        },
        "scope": "non-destructive evidence only; does not change the GLB or any source lock",
    }
    (VALIDATION / "front_mask_validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
