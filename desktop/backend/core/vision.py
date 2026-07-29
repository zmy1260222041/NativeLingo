"""Macro object detection for the Memorizing module (FR-13).

Runs a YOLOv8n model exported to ONNX directly via onnxruntime (no
ultralytics / opencv dependency) so everyday objects in a photo get a label
+ a bounding box the frontend turns into a clickable hotspot. Labels are
English (COCO class names) with a hand-authored Chinese gloss shipped next
to the model, so the learner sees the target language + their native language.

Design mirrors the rest of core/: a lazily-loaded singleton behind
``functools.lru_cache`` (see phoneme.py), a bundled-model path resolved via the
sys.frozen idiom (see transcribe.py), and an ``unload()`` for the
/memorize/release RAM-management path. The letterbox / NMS / rescale math is
exposed as pure functions so it can be unit-tested without the model.
"""
from __future__ import annotations

import functools
import json
import os
import sys

import numpy as np

# Input side of the exported model (ultralytics default: 640x640, NCHW float32).
_IN_SIZE = 640

# Prefer a pre-bundled model so the frozen app recognizes offline (no 12MB
# first-run download). Depth differs between the frozen onedir and dev:
#   frozen: <bundle>/backend/core/ -> ../../models = <bundle>/models
#   dev:    desktop/backend/core/  -> ../../../models = <repo>/models
_HERE = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, "frozen", False):
    _BUNDLED_MODEL = os.path.join(_HERE, "..", "..", "models", "yolov8n-coco")
else:
    _BUNDLED_MODEL = os.path.join(_HERE, "..", "..", "..", "models", "yolov8n-coco")

# HF fallback id if the local dir is absent (downloaded to ~/.cache on first use).
_FALLBACK_REPO = "onnx-community/yolov8n-detect-ONNX"
_FALLBACK_FILE = "onnx/model.onnx"


def _model_dir() -> str | None:
    return _BUNDLED_MODEL if os.path.isdir(_BUNDLED_MODEL) else None


@functools.lru_cache(maxsize=1)
def _load():
    """Load the ONNX session + the EN/ZH label lists. Returns
    (session, names_en, names_zh)."""
    import onnxruntime as ort

    # Labels are tracked source in core/ (coco_names.txt + coco_zh.json),
    # committed and staged by freeze.spec next to calibration.json -- so they
    # are always present regardless of where the onnx weight lives.
    with open(os.path.join(_HERE, "coco_names.txt"), encoding="utf-8") as f:
        names_en = [ln.strip() for ln in f if ln.strip()]
    with open(os.path.join(_HERE, "coco_zh.json"), encoding="utf-8") as f:
        names_zh = json.load(f)

    model_dir = _model_dir()
    if model_dir:
        onnx_path = os.path.join(model_dir, "yolov8n.onnx")
    else:
        # Lazy HF download (dev / unbundled). Best-effort; the gate (R-13) and
        # the frozen app run where the bundle is staged.
        from huggingface_hub import hf_hub_download
        onnx_path = hf_hub_download(_FALLBACK_REPO, _FALLBACK_FILE)

    # CPU EP: yolov8n at 640^2 is ~30 ms on CPU, and the frozen onnxruntime
    # wheel is not guaranteed to ship the CoreML EP. (First direct onnxruntime
    # import in the codebase.)
    session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    return session, names_en, names_zh


def is_available() -> bool:
    try:
        _load()
        return True
    except Exception:  # noqa: BLE001
        return False


def unload() -> None:
    """Release the session so /memorize/release can free RAM. The YOLO model is
    tiny + bundled, so callers usually keep it resident; this is here for
    symmetry with parts/scenario."""
    _load.cache_clear()
    import gc
    gc.collect()


# --------------------------------------------------------------------------- #
# Pure preprocessing / postprocessing (unit-tested without the model)
# --------------------------------------------------------------------------- #
def letterbox(img_size_wh, new_size=_IN_SIZE):
    """Compute the letterbox transform for an image of (w, h).

    Returns (ratio, pad_x, pad_y): scale applied to the image, and the left/top
    padding (in input pixels) added to reach new_size. A box coordinate (cx, cy)
    in the letterboxed input maps back to the original via
    ``((cx - pad_x) / ratio, (cy - pad_y) / ratio)``.
    """
    w, h = img_size_wh
    ratio = min(new_size / h, new_size / w)
    nw, nh = round(w * ratio), round(h * ratio)
    pad_x = (new_size - nw) / 2.0
    pad_y = (new_size - nh) / 2.0
    return ratio, pad_x, pad_y


def _prepare_tensor(pil_img):
    """Letterbox + normalize a PIL image into a 1x3xHxW float32 numpy array."""
    from PIL import Image

    w, h = pil_img.size
    ratio, pad_x, pad_y = letterbox((w, h))
    nw, nh = int(round(w * ratio)), int(round(h * ratio))
    resized = pil_img.resize((nw, nh), Image.BILINEAR)
    canvas = Image.new("RGB", (_IN_SIZE, _IN_SIZE), (114, 114, 114))
    canvas.paste(resized, (int(round(pad_x)), int(round(pad_y))))
    arr = np.asarray(canvas, dtype=np.float32) / 255.0  # HWC
    arr = np.transpose(arr, (2, 0, 1))[None]             # NCHW
    return np.ascontiguousarray(arr), ratio, pad_x, pad_y


def _nms(boxes_xyxy, scores, iou_thr):
    """Greedy per-image NMS (classes already filtered by caller). Returns the
    kept indices, sorted by score desc. Pure numpy, no cv2/torchvision."""
    order = np.argsort(scores)[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(int(i))
        if order.size == 1:
            break
        rest = order[1:]
        # IoU of box i vs the rest
        xx1 = np.maximum(boxes_xyxy[i, 0], boxes_xyxy[rest, 0])
        yy1 = np.maximum(boxes_xyxy[i, 1], boxes_xyxy[rest, 1])
        xx2 = np.minimum(boxes_xyxy[i, 2], boxes_xyxy[rest, 2])
        yy2 = np.minimum(boxes_xyxy[i, 3], boxes_xyxy[rest, 3])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        area_i = (boxes_xyxy[i, 2] - boxes_xyxy[i, 0]) * (boxes_xyxy[i, 3] - boxes_xyxy[i, 1])
        area_rest = (boxes_xyxy[rest, 2] - boxes_xyxy[rest, 0]) * (boxes_xyxy[rest, 3] - boxes_xyxy[rest, 1])
        iou = inter / (area_i + area_rest - inter + 1e-9)
        order = rest[iou <= iou_thr]
    return keep


def _parse_output(raw, conf, iou, ratio, pad_x, pad_y, orig_wh):
    """Turn the raw YOLOv8 ONNX output into a list of detection dicts.

    Output layout (ultralytics non-NMS export) is [1, 84, 8400]: 4 box coords
    (cx, cy, w, h in input pixels) + 80 class scores. We handle the transposed
    [1, 8400, 84] layout too, defensively.
    """
    pred = raw[0]
    if pred.shape[0] == 84 and pred.shape[1] != 84:   # [84, 8400] -> [8400, 84]
        pred = pred.T
    # pred: [N, 84]
    xywh = pred[:, :4].copy()
    cls_scores = pred[:, 4:]
    class_ids = cls_scores.argmax(axis=1)
    scores = cls_scores.max(axis=1)

    mask = scores >= conf
    xywh, scores, class_ids = xywh[mask], scores[mask], class_ids[mask]
    if len(scores) == 0:
        return []

    # cx,cy,w,h (input px) -> xyxy (input px)
    cx, cy, bw, bh = xywh[:, 0], xywh[:, 1], xywh[:, 2], xywh[:, 3]
    xyxy = np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], axis=1)
    keep = _nms(xyxy, scores, iou)

    ow, oh = orig_wh
    out = []
    for k in keep:
        x1, y1, x2, y2 = xyxy[k]
        # inverse letterbox -> original-image pixels
        x1 = (x1 - pad_x) / ratio
        y1 = (y1 - pad_y) / ratio
        x2 = (x2 - pad_x) / ratio
        y2 = (y2 - pad_y) / ratio
        # clamp + [x, y, w, h]
        x1 = float(min(max(x1, 0), ow))
        y1 = float(min(max(y1, 0), oh))
        x2 = float(min(max(x2, 0), ow))
        y2 = float(min(max(y2, 0), oh))
        out.append({
            "cls": int(class_ids[k]),
            "score": round(float(scores[k]), 3),
            "box": [round(x1, 1), round(y1, 1), round(x2 - x1, 1), round(y2 - y1, 1)],
        })
    return out


def detect(pil_img, conf=0.25, iou=0.45, max_det=50):
    """Detect whole objects in a PIL image. Returns a list of
    ``{id, label_en, label_zh, score, box:[x,y,w,h]}`` (box in original-image
    pixels, top-left + size)."""
    session, names_en, names_zh = _load()
    inp, ratio, pad_x, pad_y = _prepare_tensor(pil_img)
    inp_name = session.get_inputs()[0].name
    out_name = session.get_outputs()[0].name
    raw = session.run([out_name], {inp_name: inp})[0]
    dets = _parse_output(raw, conf, iou, ratio, pad_x, pad_y, pil_img.size)
    dets = sorted(dets, key=lambda d: d["score"], reverse=True)[:max_det]
    result = []
    for i, d in enumerate(dets):
        cid = d["cls"]
        result.append({
            "id": i,
            "label_en": names_en[cid] if cid < len(names_en) else f"class-{cid}",
            "label_zh": names_zh[cid] if cid < len(names_zh) else "",
            "score": d["score"],
            "box": d["box"],
        })
    return result
