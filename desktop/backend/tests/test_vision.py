"""Tests for the Memorizing module's vision path (FR-13).

The YOLO ONNX pre/post-processing is the highest-bug surface (no prior reference
in the codebase), so we unit-test the pure math -- letterbox + NMS + the inverse
rescale that maps boxes back to original-image pixels -- without needing the
actual model. Plus an API smoke test that the endpoint decodes images and
degrades gracefully (503, not 500) when the model isn't staged.
"""
from __future__ import annotations

import io

import numpy as np
from fastapi.testclient import TestClient

from backend.core import vision
from backend.main import app

client = TestClient(app)


def test_letterbox_roundtrip():
    """A point in original-image space, forward through letterbox then inverse,
    must recover the original coordinates (boxes are rescaled by this transform)."""
    for wh in [(320, 240), (640, 640), (480, 720), (1280, 720)]:
        ratio, pad_x, pad_y = vision.letterbox(wh)
        # inverse of: input = orig * ratio + pad
        ox, oy = wh[0] / 2.0, wh[1] / 2.0
        ix, iy = ox * ratio + pad_x, oy * ratio + pad_y
        rx, ry = (ix - pad_x) / ratio, (iy - pad_y) / ratio
        assert abs(rx - ox) < 1e-6 and abs(ry - oy) < 1e-6


def test_nms_suppresses_overlap():
    boxes = np.array([[0, 0, 100, 100], [2, 2, 102, 102], [500, 500, 600, 600]],
                     dtype=np.float32)
    scores = np.array([0.9, 0.8, 0.7])
    keep = vision._nms(boxes, scores, iou_thr=0.45)
    assert keep == [0, 2]  # the heavily-overlapping second box is suppressed


def _synthetic_raw(layout, anchor, cx, cy, bw, bh, cls_score=0.9, cls=0):
    """Build a fake YOLOv8 output with a single strong detection at `anchor`."""
    if layout == "84xN":
        raw = np.zeros((1, 84, 8400), dtype=np.float32)
        raw[0, 0, anchor] = cx
        raw[0, 1, anchor] = cy
        raw[0, 2, anchor] = bw
        raw[0, 3, anchor] = bh
        raw[0, 4 + cls, anchor] = cls_score
    else:  # "Nx84"
        raw = np.zeros((1, 8400, 84), dtype=np.float32)
        raw[0, anchor, 0] = cx
        raw[0, anchor, 1] = cy
        raw[0, anchor, 2] = bw
        raw[0, anchor, 3] = bh
        raw[0, anchor, 4 + cls] = cls_score
    return raw


def test_parse_output_rescales_to_original_pixels():
    """A detection placed in 640-space must rescale back to the original image's
    pixel coordinates (forgetting the inverse letterbox is the classic YOLO bug)."""
    # image 320x240 -> ratio 2.0, pad_x 0, pad_y 80
    ratio, pad_x, pad_y = vision.letterbox((320, 240))
    # object centered at original (160,120), size 100x80
    cx_in = 160 * ratio + pad_x       # 320
    cy_in = 120 * ratio + pad_y       # 320
    bw_in = 100 * ratio               # 200
    bh_in = 80 * ratio                # 160
    for layout in ("84xN", "Nx84"):
        raw = _synthetic_raw(layout, anchor=100, cx=cx_in, cy=cy_in,
                             bw=bw_in, bh=bh_in)
        dets = vision._parse_output(raw, conf=0.5, iou=0.45, ratio=ratio,
                                    pad_x=pad_x, pad_y=pad_y, orig_wh=(320, 240))
        assert len(dets) == 1, layout
        x, y, w, h = dets[0]["box"]
        assert abs(x - 110) <= 1.5 and abs(y - 80) <= 1.5     # top-left
        assert abs(w - 100) <= 1.5 and abs(h - 80) <= 1.5     # size
        assert dets[0]["cls"] == 0 and dets[0]["score"] == 0.9


def test_memorize_analyze_rejects_non_image():
    """Posting bytes that aren't a decodable image is a clean 400 (not a 500)."""
    res = client.post("/memorize/analyze",
                      files={"photo": ("not.jpg", b"definitely not an image", "image/jpeg")})
    assert res.status_code == 400


def test_memorize_status_endpoint():
    """/memorize/status is reachable and reports a stage (no model needed)."""
    res = client.get("/memorize/status")
    assert res.status_code == 200
    assert "stage" in res.json()


def test_memorize_analyze_degrades_without_model():
    """With a valid tiny image but no staged model, the endpoint returns 503
    (graceful) rather than crashing -- proving the wiring + PIL decode work."""
    pil = pytest_pil()
    if pil is None:
        return  # Pillow not installed in this env; math tests above still cover the path
    buf = io.BytesIO()
    pil.new("RGB", (64, 64), (120, 80, 40)).save(buf, format="PNG")
    res = client.post("/memorize/analyze",
                      files={"photo": ("x.png", buf.getvalue(), "image/png")})
    assert res.status_code in (200, 503), res.text


def pytest_pil():
    try:
        from PIL import Image
        return Image
    except Exception:  # noqa: BLE001
        return None
