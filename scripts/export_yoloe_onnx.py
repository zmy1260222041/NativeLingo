#!/usr/bin/env python3
"""Create NativeLingo's pinned detection-only YOLOE-26S-PF ONNX artifact.

Build-time requirements (not shipped in the app):

    pip install ultralytics==8.4.110 onnx==1.22.0

The official PF checkpoint is a segmentation model.  NativeLingo only needs
hotspot boxes, so this export binds the detection forward path, bakes in the
LRPC proposal threshold, limits candidates to 50, and exports dynamic
rectangular inputs.  The resulting app still runs with onnxruntime alone.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

SOURCE_SIZE = 32_696_887
SOURCE_SHA256 = "9f0cefea64c48103a917dbc8ea4baf581aaf6ffa286675861dafd6fd04826f50"
ULTRALYTICS_VERSION = "8.4.110"
PROPOSAL_CONFIDENCE = 0.10
MAX_DETECTIONS = 50
_REPO = Path(__file__).resolve().parent.parent


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _allowed_labels() -> set[str]:
    config = json.loads(
        (_REPO / "desktop/backend/core/yoloe_labels.json").read_text(
            encoding="utf-8"
        )
    )
    coco = {
        line.strip()
        for line in (
            _REPO / "desktop/backend/core/coco_names.txt"
        ).read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    coco.discard("person")
    return coco | set(config["labels"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", required=True, type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("models/yoloe-26s-pf/yoloe-26s-pf.onnx"),
    )
    args = parser.parse_args()

    if args.weights.stat().st_size != SOURCE_SIZE:
        raise SystemExit("official YOLOE checkpoint size mismatch")
    if _sha256(args.weights) != SOURCE_SHA256:
        raise SystemExit("official YOLOE checkpoint SHA-256 mismatch")

    import onnx
    import torch
    import ultralytics
    from ultralytics import YOLOE
    from ultralytics.nn.modules.head import YOLOEDetect, YOLOESegment26

    if ultralytics.__version__ != ULTRALYTICS_VERSION:
        raise SystemExit(
            f"ultralytics {ULTRALYTICS_VERSION} required; "
            f"found {ultralytics.__version__}"
        )

    def curated_postprocess(self, predictions):
        """Discard non-tangible classes before YOLOE's global top-k."""
        boxes, scores = predictions.split([4, self.nc], dim=-1)
        scores = scores * self.native_lingo_class_mask
        scores, confidence, index = self.get_topk_index(scores, self.max_det)
        boxes = boxes.gather(dim=1, index=index.expand(-1, -1, 4))
        return torch.cat([boxes, scores, confidence], dim=-1)

    # Remove segmentation output while retaining the PF classification head.
    # Filtering the 4,585-class score tensor before global top-k prevents noisy
    # action/scene labels from crowding tangible objects out of the 50 outputs.
    YOLOESegment26.forward = YOLOEDetect.forward
    YOLOESegment26.forward_lrpc = YOLOEDetect.forward_lrpc
    YOLOESegment26._inference = YOLOEDetect._inference
    YOLOESegment26.postprocess = curated_postprocess

    with tempfile.TemporaryDirectory(prefix="nativelingo-yoloe-export-") as temp:
        temp_dir = Path(temp)
        staged_weights = temp_dir / "yoloe-26s-pf-detect.pt"
        shutil.copyfile(args.weights, staged_weights)

        model = YOLOE(str(staged_weights))
        model.task = "detect"
        model.model.task = "detect"
        model.model.args["task"] = "detect"
        head = model.model.model[-1]
        head.conf = PROPOSAL_CONFIDENCE
        allowed = _allowed_labels()
        class_mask = torch.tensor(
            [
                1.0 if str(model.names[index]) in allowed else 0.0
                for index in range(head.nc)
            ],
            dtype=torch.float32,
        ).view(1, 1, -1)
        head.register_buffer("native_lingo_class_mask", class_mask)
        exported = Path(
            model.export(
                format="onnx",
                imgsz=640,
                opset=20,
                simplify=False,
                dynamic=True,
                nms=False,
                max_det=MAX_DETECTIONS,
            )
        )

        graph = onnx.load(exported)
        metadata = {entry.key: entry for entry in graph.metadata_props}
        updates = {
            "date": "2026-07-30",
            "description": (
                "NativeLingo YOLOE-26S-PF tangible-object detector; "
                "curated pre-top-k vocabulary, dynamic rectangular input, "
                f"proposal confidence {PROPOSAL_CONFIDENCE:.2f}, max_det 50"
            ),
            "native_lingo_proposal_conf": f"{PROPOSAL_CONFIDENCE:.2f}",
            "native_lingo_max_det": str(MAX_DETECTIONS),
            "native_lingo_output": "xyxy_score_class",
            "native_lingo_pre_topk_label_count": str(int(class_mask.sum().item())),
            "native_lingo_source": (
                "ultralytics/assets v8.4.0 yoloe-26s-seg-pf.pt"
            ),
        }
        for key, value in updates.items():
            if key in metadata:
                metadata[key].value = value
            else:
                entry = graph.metadata_props.add()
                entry.key = key
                entry.value = value

        args.output.parent.mkdir(parents=True, exist_ok=True)
        onnx.save(graph, args.output)

    print(f"{args.output}  {args.output.stat().st_size} bytes  {_sha256(args.output)}")


if __name__ == "__main__":
    main()
