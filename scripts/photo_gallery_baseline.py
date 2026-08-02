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

def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return ordered[index]


def _latency_bucket(
    values: list[float],
    *,
    p95_target_ms: float,
    max_target_ms: float | None = None,
) -> dict:
    p95 = _percentile(values, 0.95)
    maximum = max(values, default=0.0)
    summary = {
        "photo_count": len(values),
        "median_ms": round(statistics.median(values), 1) if values else 0.0,
        "p95_ms": round(p95, 1),
        "max_ms": round(maximum, 1),
        "p95_target_ms": p95_target_ms,
        "p95_within_target": bool(values) and p95 <= p95_target_ms,
    }
    if max_target_ms is not None:
        summary.update(
            max_target_ms=max_target_ms,
            max_within_target=bool(values) and maximum < max_target_ms,
        )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gallery", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    gallery = Path(args.gallery)
    manifest = json.loads((gallery / "manifest.json").read_text(encoding="utf-8"))

    from backend.core import memorize_image, vision

    results = []
    latencies = []
    for item in manifest["items"]:
        path = gallery / item["file"]
        image, _canonical_bytes = memorize_image.canonicalize_upload(
            path.read_bytes()
        )

        started = time.perf_counter()
        objects = vision.detect(image)
        latency_ms = (time.perf_counter() - started) * 1000
        latencies.append(latency_ms)
        multiscale = max(image.size) >= vision._MULTISCALE_MIN_LONG_SIDE

        result = {
            "file": item["file"],
            "scene": item["scene"],
            "size": list(image.size),
            "multiscale": multiscale,
            "latency_ms": round(latency_ms, 1),
            "objects": objects,
        }
        results.append(result)
        print(
            f'{item["file"]:42} '
            f"YOLOE {len(objects):2d} / {latency_ms:6.1f}ms"
        )

    small_latencies = [
        row["latency_ms"] for row in results if not row["multiscale"]
    ]
    multiscale_latencies = [
        row["latency_ms"] for row in results if row["multiscale"]
    ]
    payload = {
        "model": "YOLOE-26S-PF detection-only ONNX + curated tangible vocabulary",
        "preprocessing": memorize_image.CONTRACT_VERSION,
        "photo_count": len(results),
        "summary": {
            "detection_count": sum(len(row["objects"]) for row in results),
            "unique_labels": sorted(
                {obj["label_en"] for row in results for obj in row["objects"]}
            ),
            "zero_result_photos": sum(not row["objects"] for row in results),
            "median_ms": round(statistics.median(latencies), 1),
            "p95_ms": round(_percentile(latencies, 0.95), 1),
            "latency_buckets": {
                "small_global_only": _latency_bucket(
                    small_latencies,
                    p95_target_ms=200,
                ),
                "large_global_multiscale": _latency_bucket(
                    multiscale_latencies,
                    p95_target_ms=8000,
                    max_target_ms=12000,
                ),
            },
            "threshold_policy": (
                f"{len(vision._load()[2])}-label pre-top-k vocabulary "
                "at proposal confidence 0.10 "
                "+ per-label minimum score + class-agnostic IoU 0.72 "
                "+ global 640px pass + 1280px inference over 5/12-long-side "
                "tiles at 50% overlap + internal-edge clipping rejection "
                "+ canonical EXIF/LANCZOS/Q90 model input"
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
