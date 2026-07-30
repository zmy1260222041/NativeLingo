#!/usr/bin/env python3
"""Run NativeLingo's shipped YOLOE detector on the local evaluation gallery."""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "desktop"))

from PIL import Image  # noqa: E402


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gallery", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    gallery = Path(args.gallery)
    manifest = json.loads((gallery / "manifest.json").read_text(encoding="utf-8"))

    from backend.core import vision

    results = []
    latencies = []
    for item in manifest["items"]:
        path = gallery / item["file"]
        with Image.open(path) as source:
            image = source.convert("RGB")

        started = time.perf_counter()
        objects = vision.detect(image)
        latency_ms = (time.perf_counter() - started) * 1000
        latencies.append(latency_ms)

        result = {
            "file": item["file"],
            "scene": item["scene"],
            "size": list(image.size),
            "latency_ms": round(latency_ms, 1),
            "objects": objects,
        }
        results.append(result)
        print(
            f'{item["file"]:42} '
            f"YOLOE {len(objects):2d} / {latency_ms:6.1f}ms"
        )

    payload = {
        "model": "YOLOE-26S-PF detection-only ONNX + curated tangible vocabulary",
        "photo_count": len(results),
        "summary": {
            "detection_count": sum(len(row["objects"]) for row in results),
            "unique_labels": sorted(
                {obj["label_en"] for row in results for obj in row["objects"]}
            ),
            "zero_result_photos": sum(not row["objects"] for row in results),
            "median_ms": round(statistics.median(latencies), 1),
            "p95_ms": round(_percentile(latencies, 0.95), 1),
            "threshold_policy": (
                f"{len(vision._load()[2])}-label pre-top-k vocabulary "
                "at proposal confidence 0.10 "
                "+ per-label minimum score + class-agnostic IoU 0.72 "
                "+ contextual 1280px plaque detail pass"
            ),
        },
        "results": results,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + os.linesep,
        encoding="utf-8",
    )
    print(f"\nSaved {output}")


if __name__ == "__main__":
    main()
