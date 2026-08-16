#!/usr/bin/env python3
"""Make an A-pose-only modeling lock from the user-approved four-view sheet.

This is deliberately mechanical: crop only the external white letterbox bands, then
use the existing line-free orthographic preparation routine to key the near-uniform
studio field, isolate the four approved views, and register them on common canvases.
It never generates, inpaints, mirrors, or redraws Mira.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image


VIEW_ORDER = ("front", "character_left", "back", "character_right")
FIELD_BOX = (0, 88, 2172, 633)  # exact non-white field in the approved 2172x724 upload


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_prepare_module(tool_dir: Path):
    source = tool_dir / "prepare_modeling_views.py"
    spec = importlib.util.spec_from_file_location("mira_prepare_modeling_views", source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to import {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approved-source", type=Path, required=True)
    parser.add_argument("--lock-root", type=Path, required=True)
    args = parser.parse_args()

    source = args.approved_source.resolve()
    root = args.lock_root.resolve()
    raw_dir = root / "raw"
    prep_dir = root / "hunyuan_input"
    raw_dir.mkdir(parents=True, exist_ok=True)
    prep_dir.mkdir(parents=True, exist_ok=True)

    image = Image.open(source).convert("RGB")
    if image.size != (2172, 724):
        raise RuntimeError(f"Approved source must be 2172x724, got {image.size}")
    field = image.crop(FIELD_BOX)
    field_path = prep_dir / "chr_npc_mira_a_pose_active_field.png"
    field.save(field_path, optimize=True)

    prepare = load_prepare_module(Path(__file__).resolve().parent)
    report = prepare.prepare_sheet(field_path, root, "a_pose")

    copied_views = []
    for view in VIEW_ORDER:
        source_view = root / "a_pose" / f"chr_npc_mira_a_pose_{view}.png"
        target_view = prep_dir / source_view.name
        target_view.write_bytes(source_view.read_bytes())
        copied_views.append({"view": view, "file": str(target_view.relative_to(root)), "sha256": sha256(target_view)})

    contact_source = root / "chr_npc_mira_a_pose_turnaround.png"
    contact_target = prep_dir / contact_source.name
    contact_target.write_bytes(contact_source.read_bytes())

    report.update(
        {
            "lock_scope": "A_POSE_ONLY",
            "t_pose_status": "UNLOCKED_NOT_INCLUDED",
            "user_approved_source": str(source),
            "user_approved_source_sha256": sha256(source),
            "white_letterbox_crop_xyxy": list(FIELD_BOX),
            "active_field": str(field_path.relative_to(root)),
            "active_field_size": list(field.size),
            "active_field_sha256": sha256(field_path),
            "hunyuan_multiview_input": copied_views,
            "hunyuan_contact_sheet": str(contact_target.relative_to(root)),
            "hunyuan_contact_sheet_sha256": sha256(contact_target),
            "processing": "crop external white bands; existing alpha key/background normalization/canvas registration only",
            "forbidden_operations": ["generation", "inpainting", "redrawing", "mirroring", "structural edit"],
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        }
    )
    (root / "a_pose_processing_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"lock_root": str(root), "views": copied_views, "report": str(root / "a_pose_processing_report.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
