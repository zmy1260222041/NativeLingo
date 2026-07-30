"""YOLOE-26S-PF macro object detection for the Memorizing module (FR-13).

The model is a detection-only ONNX export of Ultralytics' prompt-free
YOLOE-26S segmentation checkpoint.  It keeps YOLOE's open vocabulary but
removes the unused mask branch from the exported output.  Runtime inference is
direct onnxruntime: Ultralytics, PyTorch and OpenCV are build-time only.

Prompt-free YOLOE exposes thousands of labels, including actions, scene types
and noisy training aliases.  Showing all of them is actively harmful in a
language-learning UI, so ``yoloe_labels.json`` is both:

* a tangible-object allowlist; and
* a per-label confidence calibration table.

Unknown labels are discarded.  A conservative COCO vocabulary is merged in so
common objects remain available, while ``person`` is deliberately omitted to
avoid covering a photo with human hotspots.
"""
from __future__ import annotations

import ast
import functools
import json
import math
import os
import sys

import numpy as np

from backend.core import model_assets

_IN_SIZE = 640
_DETAIL_IN_SIZE = 1280
_DETAIL_MIN_LONG_SIDE = 960
_DETAIL_LABELS = frozenset({"plaque"})
_DETAIL_CONTEXT_LABELS = frozenset({"clock", "cabinet", "showcase"})
_STRIDE = 32
_HERE = os.path.dirname(os.path.abspath(__file__))
_MODEL_FILENAME = model_assets.YOLO_FILENAME

if getattr(sys, "frozen", False):
    _BUNDLED_MODEL = os.path.join(_HERE, "..", "..", "models", "yoloe-26s-pf")
else:
    _BUNDLED_MODEL = os.path.join(
        _HERE, "..", "..", "..", "models", "yoloe-26s-pf"
    )


def _model_path() -> str:
    path = os.path.join(_BUNDLED_MODEL, _MODEL_FILENAME)
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"{_MODEL_FILENAME} is not staged; run scripts/export_yoloe_onnx.py"
        )
    return path


def _load_label_specs(model_names: dict[int, str]) -> dict[str, dict]:
    """Build the curated label → {zh, min_score} table.

    COCO supplies conservative coverage for familiar objects; explicit YOLOE
    entries override its translation and threshold.  A label absent from the
    resulting mapping can never reach the UI.
    """
    with open(os.path.join(_HERE, "coco_names.txt"), encoding="utf-8") as handle:
        coco_en = [line.strip() for line in handle if line.strip()]
    with open(os.path.join(_HERE, "coco_zh.json"), encoding="utf-8") as handle:
        coco_zh = json.load(handle)
    with open(os.path.join(_HERE, "yoloe_labels.json"), encoding="utf-8") as handle:
        config = json.load(handle)

    available = set(model_names.values())
    default_score = float(config["_default_coco_min_score"])
    specs = {}
    for label_en, label_zh in zip(coco_en, coco_zh):
        if label_en == "person" or label_en not in available:
            continue
        specs[label_en] = {"zh": label_zh, "min_score": default_score}

    for label_en, spec in config["labels"].items():
        if label_en not in available:
            continue
        specs[label_en] = {
            "zh": str(spec["zh"]),
            "min_score": float(spec["min_score"]),
        }
    return specs


@functools.lru_cache(maxsize=1)
def _load():
    """Load and validate the ONNX model plus its embedded class vocabulary."""
    import onnxruntime as ort

    path = model_assets.verify_file(
        _model_path(),
        model_assets.YOLO_SIZE,
        model_assets.YOLO_SHA256,
    )
    session = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    metadata = session.get_modelmeta().custom_metadata_map

    if metadata.get("end2end") != "True" or metadata.get("task") != "detect":
        raise model_assets.ModelIntegrityError(
            "YOLOE ONNX metadata is not the NativeLingo end-to-end detect export"
        )
    if metadata.get("native_lingo_proposal_conf") != "0.10":
        raise model_assets.ModelIntegrityError("unexpected YOLOE proposal threshold")
    if metadata.get("native_lingo_max_det") != "50":
        raise model_assets.ModelIntegrityError("unexpected YOLOE candidate limit")
    if metadata.get("native_lingo_pre_topk_label_count") != "177":
        raise model_assets.ModelIntegrityError(
            "YOLOE ONNX is missing the curated pre-top-k vocabulary filter"
        )

    try:
        raw_names = ast.literal_eval(metadata["names"])
        names = {int(index): str(label) for index, label in raw_names.items()}
    except (KeyError, SyntaxError, TypeError, ValueError) as exc:
        raise model_assets.ModelIntegrityError(
            "YOLOE ONNX has no usable embedded class vocabulary"
        ) from exc
    if len(names) < 1_200:
        raise model_assets.ModelIntegrityError(
            f"YOLOE vocabulary is unexpectedly small ({len(names)} labels)"
        )

    return session, names, _load_label_specs(names)


def is_available() -> bool:
    try:
        _load()
        return True
    except Exception:  # noqa: BLE001
        return False


def unload() -> None:
    _load.cache_clear()
    model_assets.verify_file.cache_clear()
    import gc

    gc.collect()


def letterbox(img_size_wh, new_size=_IN_SIZE, stride=_STRIDE):
    """Return the rectangular letterbox transform used by dynamic YOLOE.

    The longest side is scaled to ``new_size`` and the shorter side is padded
    only to the next stride multiple.  Returns
    ``(ratio, pad_x, pad_y, input_width, input_height)``.
    """
    width, height = img_size_wh
    ratio = min(new_size / width, new_size / height)
    resized_width = max(1, int(round(width * ratio)))
    resized_height = max(1, int(round(height * ratio)))
    input_width = min(new_size, int(math.ceil(resized_width / stride) * stride))
    input_height = min(new_size, int(math.ceil(resized_height / stride) * stride))
    pad_x = int(round((input_width - resized_width) / 2 - 0.1))
    pad_y = int(round((input_height - resized_height) / 2 - 0.1))
    return ratio, pad_x, pad_y, input_width, input_height


def _prepare_tensor(pil_img, new_size=_IN_SIZE):
    from PIL import Image

    ratio, pad_x, pad_y, input_width, input_height = letterbox(
        pil_img.size, new_size=new_size
    )
    resized_width = int(round(pil_img.size[0] * ratio))
    resized_height = int(round(pil_img.size[1] * ratio))
    resized = pil_img.resize(
        (resized_width, resized_height), Image.Resampling.BILINEAR
    )
    canvas = Image.new("RGB", (input_width, input_height), (114, 114, 114))
    canvas.paste(resized, (pad_x, pad_y))
    array = np.asarray(canvas, dtype=np.float32) / 255.0
    array = np.transpose(array, (2, 0, 1))[None]
    return np.ascontiguousarray(array), ratio, pad_x, pad_y


def _run(session, pil_img, *, new_size=_IN_SIZE):
    """Run one dynamic-shape YOLOE pass and return its geometry metadata."""
    tensor, ratio, pad_x, pad_y = _prepare_tensor(pil_img, new_size=new_size)
    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[0].name
    raw = session.run([output_name], {input_name: tensor})[0]
    return raw, ratio, pad_x, pad_y


def _box_iou(a, b) -> float:
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    inter = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(
        0.0, min(ay2, by2) - max(ay1, by1)
    )
    return inter / (aw * ah + bw * bh - inter + 1e-9)


def _box_containment(a, b) -> float:
    """Intersection divided by the smaller box, for nested alias boxes."""
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    inter = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(
        0.0, min(ay2, by2) - max(ay1, by1)
    )
    return inter / (min(aw * ah, bw * bh) + 1e-9)


def _labels_are_nested_aliases(first: str, second: str) -> bool:
    first_words = set(first.split())
    second_words = set(second.split())
    return first_words <= second_words or second_words <= first_words


def _detail_detection_is_usable(detection: dict) -> bool:
    """Apply geometry checks only to labels recovered by the detail pass."""
    if detection["label_en"] == "plaque":
        _, _, width, height = detection["box"]
        aspect_ratio = width / max(height, 1e-9)
        return 1.6 <= aspect_ratio <= 2.5
    return True


def _parse_output(
    raw,
    *,
    ratio,
    pad_x,
    pad_y,
    orig_wh,
    names,
    label_specs,
    confidence_floor=0.0,
    dedupe_iou=0.72,
    max_det=40,
):
    """Filter YOLOE's ``[x1,y1,x2,y2,score,class]`` end-to-end output."""
    prediction = np.asarray(raw)
    if prediction.ndim == 3:
        prediction = prediction[0]
    if prediction.ndim != 2 or prediction.shape[1] != 6:
        raise RuntimeError(f"unexpected YOLOE output shape {prediction.shape}")

    orig_width, orig_height = orig_wh
    candidates = []
    for row in prediction:
        score = float(row[4])
        class_id = int(round(float(row[5])))
        label_en = names.get(class_id)
        spec = label_specs.get(label_en)
        if spec is None:
            continue
        if score < max(float(spec["min_score"]), confidence_floor):
            continue

        x1 = min(max((float(row[0]) - pad_x) / ratio, 0.0), orig_width)
        y1 = min(max((float(row[1]) - pad_y) / ratio, 0.0), orig_height)
        x2 = min(max((float(row[2]) - pad_x) / ratio, 0.0), orig_width)
        y2 = min(max((float(row[3]) - pad_y) / ratio, 0.0), orig_height)
        width = x2 - x1
        height = y2 - y1
        if width < 2.0 or height < 2.0:
            continue
        candidates.append(
            {
                "label_en": label_en,
                "label_zh": spec["zh"],
                "score": round(score, 3),
                "box": [
                    round(x1, 1),
                    round(y1, 1),
                    round(width, 1),
                    round(height, 1),
                ],
            }
        )

    candidates.sort(key=lambda item: item["score"], reverse=True)
    kept = []
    for candidate in candidates:
        # Prompt-free vocabulary often emits synonyms for exactly the same
        # region (mug/cup, sofa/couch).  Keep only the highest-confidence term.
        if any(
            _box_iou(candidate["box"], prior["box"]) >= dedupe_iou
            or (
                _labels_are_nested_aliases(
                    candidate["label_en"], prior["label_en"]
                )
                and _box_containment(candidate["box"], prior["box"]) >= 0.88
            )
            for prior in kept
        ):
            continue
        kept.append(candidate)
        if len(kept) >= max_det:
            break

    for index, item in enumerate(kept):
        item["id"] = index
    return kept


def detect(
    pil_img,
    confidence_floor=0.0,
    dedupe_iou=0.72,
    max_det=40,
):
    """Return curated open-vocabulary objects with original-image boxes.

    The 640px pass preserves large-scene recall and speed. On sufficiently
    large photos, a second dynamic 1280px pass contributes only explicitly
    approved small-detail labels. This retains city-name plaques without
    importing the noisier high-resolution predictions for every class.
    """
    session, names, label_specs = _load()
    raw, ratio, pad_x, pad_y = _run(session, pil_img)
    detections = _parse_output(
        raw,
        ratio=ratio,
        pad_x=pad_x,
        pad_y=pad_y,
        orig_wh=pil_img.size,
        names=names,
        label_specs=label_specs,
        confidence_floor=confidence_floor,
        dedupe_iou=dedupe_iou,
        max_det=max_det,
    )

    detail_context_found = any(
        detection["label_en"] in _DETAIL_CONTEXT_LABELS
        for detection in detections
    )
    if max(pil_img.size) >= _DETAIL_MIN_LONG_SIDE and detail_context_found:
        detail_specs = {
            label: label_specs[label]
            for label in _DETAIL_LABELS
            if label in label_specs
        }
        if detail_specs:
            detail_raw, detail_ratio, detail_pad_x, detail_pad_y = _run(
                session, pil_img, new_size=_DETAIL_IN_SIZE
            )
            details = _parse_output(
                detail_raw,
                ratio=detail_ratio,
                pad_x=detail_pad_x,
                pad_y=detail_pad_y,
                orig_wh=pil_img.size,
                names=names,
                label_specs=detail_specs,
                confidence_floor=confidence_floor,
                dedupe_iou=dedupe_iou,
                max_det=max_det,
            )
            for detail in details:
                if not _detail_detection_is_usable(detail):
                    continue
                if not any(
                    detail["label_en"] == prior["label_en"]
                    and _box_iou(detail["box"], prior["box"]) >= dedupe_iou
                    for prior in detections
                ):
                    detections.append(detail)

    detections.sort(key=lambda item: item["score"], reverse=True)
    detections = detections[:max_det]
    for index, item in enumerate(detections):
        item["id"] = index
    return detections
