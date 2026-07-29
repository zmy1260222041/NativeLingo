#!/usr/bin/env python3
"""R-13 quality gate for the Memorizing module (FR-13/14/15, NFR-5).

Runs the three on-device models on a small labeled photo set and emits the
numbers that fill docs/reviews/2026-07-29-photo-recognition-fit.md:
  * macro (YOLO):     precision / recall vs ground-truth boxes+classes
  * micro (VLM):      part-name relevance + hallucination (human-judged -> CSV)
  * scenario (LLM):   fluency / vividness / en-zh match (human-judged -> CSV)
  * latency + RSS

Objective metrics (precision/recall/latency) print to stdout; the
human-judged columns are written to a CSV for manual scoring, mirroring how the
prior gates (mdd_margin_sweep.py, ref_swap_experiment.py) pair script output
with hand review.

Prerequisites (run on a machine with network + the models staged):
  1. models/yolov8n-coco/yolov8n.onnx present (see that dir's README).
  2. VLM + LLM cached (run the app and open the Memorize tab once, or let this
     script's first run download them via transformers).

Usage:
  python scripts/photo_gate.py --photos path/to/photos [--labels labels.json]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time

# allow running from repo root without installing the package
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)
_DESKTOP = os.path.join(_REPO, "desktop")
if os.path.isdir(_DESKTOP):
    sys.path.insert(0, _DESKTOP)

from PIL import Image  # noqa: E402


def _iou(a, b):
    ax1, ay1 = a[0], a[1]
    ax2, ay2 = a[0] + a[2], a[1] + a[3]
    bx1, by1 = b[0], b[1]
    bx2, by2 = b[0] + b[2], b[1] + b[3]
    inter = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(0.0, min(ay2, by2) - max(ay1, by1))
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    return inter / (area_a + area_b - inter + 1e-9)


def run_macro(photos, labels, vision):
    rows = []
    tp = fp = fn = 0
    for ph in photos:
        img = Image.open(ph).convert("RGB")
        t0 = time.time()
        dets = vision.detect(img)
        lat = (time.time() - t0) * 1000
        gts = []
        if labels:
            entry = labels.get(os.path.basename(ph), {})
            gts = [{"label": g["label"], "box": g["box"]} for g in entry.get("objects", [])]
        matched = set()
        for d in dets:
            hit = None
            for gi, g in enumerate(gts):
                if gi in matched:
                    continue
                if d["label_en"].lower() == g["label"].lower() and _iou(d["box"], g["box"]) >= 0.5:
                    hit = gi
                    break
            if hit is not None:
                matched.add(hit)
                tp += 1
            else:
                fp += 1
        fn += len(gts) - len(matched)
        rows.append((os.path.basename(ph), len(dets), len(gts), f"{lat:.0f}ms"))
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return rows, precision, recall


def run_micro(photos, labels, parts, out_csv):
    """Run the VLM on one crop per labeled object; dump for human relevance /
    hallucination scoring (columns: photo, object, predicted_parts, score, is_halluc)."""
    to_score = []
    for ph in photos:
        if not labels:
            continue
        entry = labels.get(os.path.basename(ph), {})
        img = Image.open(ph).convert("RGB")
        for g in entry.get("objects", []):
            x, y, w, h = g["box"]
            crop = img.crop((int(x), int(y), int(x + w), int(y + h)))
            t0 = time.time()
            try:
                res = parts.name_parts(crop, g["label"], g.get("label_zh", ""))
            except Exception as e:  # noqa: BLE001
                res = [{"label_en": f"ERROR: {e}", "label_zh": ""}]
            lat = (time.time() - t0)
            names = "; ".join(f'{p["label_en"]}/{p["label_zh"]}' for p in res)
            to_score.append([os.path.basename(ph), g["label"], names, "", "", f"{lat:.1f}s"])
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["photo", "object", "predicted_parts", "relevance(0/0.5/1)", "is_halluc(0/1)", "latency"])
        w.writerows(to_score)
    return len(to_score)


def run_scenario(labels, scenario, out_csv):
    to_score = []
    items = []
    if labels:
        for entry in labels.values():
            for g in entry.get("objects", []):
                items.append((g["label"], g.get("label_zh", "")))
    for en, zh in items[:40]:
        t0 = time.time()
        try:
            sents = scenario.generate(en, zh)
        except Exception as e:  # noqa: BLE001
            sents = [{"en": f"ERROR: {e}", "zh": ""}]
        lat = time.time() - t0
        for s in sents:
            to_score.append([en, s.get("en", ""), s.get("zh", ""), "", "", "", f"{lat:.1f}s"])
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["object", "en", "zh", "fluency(1-5)", "vividness(1-5)", "en_zh_match(0/1)", "latency"])
        w.writerows(to_score)
    return len(to_score)


def rss_mb():
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # macOS: bytes->KB already? ru_maxrss is KB on mac
    except Exception:  # noqa: BLE001
        return 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--photos", required=True, help="photo file or directory")
    ap.add_argument("--labels", help="JSON: {filename: {objects:[{label,label_zh,box:[x,y,w,h]}]}}")
    ap.add_argument("--skip-vlm", action="store_true")
    ap.add_argument("--skip-llm", action="store_true")
    args = ap.parse_args()

    if os.path.isdir(args.photos):
        photos = sorted(
            os.path.join(args.photos, f) for f in os.listdir(args.photos)
            if f.lower().endswith((".jpg", ".jpeg", ".png"))
        )
    else:
        photos = [args.photos]

    labels = None
    if args.labels:
        with open(args.labels, encoding="utf-8") as f:
            labels = json.load(f)

    from backend.core import vision
    print("== loading YOLO (macro) ==")
    vision._load()

    print("\n== MACRO (YOLOv8n) ==")
    rows, precision, recall = run_macro(photos, labels, vision)
    print(f"{'photo':30} dets gt  latency")
    for r in rows:
        print(f"{r[0]:30} {r[1]:>4} {r[2]:>2}  {r[3]}")
    print(f"\nprecision = {precision:.3f}   (gate >= 0.80)")
    print(f"recall    = {recall:.3f}   (gate >= 0.60)")

    if not args.skip_vlm:
        from backend.core import parts
        print("\n== loading VLM (micro) ==")
        parts._load()
        out = os.path.join(_REPO, "docs", "reviews", "_r13_micro.csv")
        n = run_micro(photos, labels, parts, out)
        print(f"wrote {n} crops for human scoring -> {out}")

    if not args.skip_llm:
        from backend.core import scenario
        print("\n== loading LLM (scenario) ==")
        scenario._load()
        out = os.path.join(_REPO, "docs", "reviews", "_r13_scenario.csv")
        n = run_scenario(labels, scenario, out)
        print(f"wrote {n} sentences for human scoring -> {out}")

    print(f"\npeak RSS ~ {rss_mb():.0f} MB   (gate <= 12 GB co-resident with Speaking models)")
    print("\nNext: fill the human-judged columns in the CSVs, then transcribe the")
    print("numbers + verdicts into docs/reviews/2026-07-29-photo-recognition-fit.md.")


if __name__ == "__main__":
    main()
