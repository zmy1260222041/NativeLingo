#!/usr/bin/env python3
"""Container fixtures for the device-side half of Gate E (R-9).

R-9 settled the *resampler* question on the desktop: swapping the kernel moves a
calibrated score by 0.00, so the platform decoder route is safe on that axis. It
left one thing explicitly unresolved — "system decoders are per-OEM
implementations, FFmpeg would have been identical everywhere" — and that can only
be measured by handing a device a real container and comparing what comes out.

This script builds the pair that makes such a comparison possible:

  1. a container the device can decode (mp4/AAC and webm/Opus, encoded from the
     golden clip at 44.1 kHz stereo, because that is the shape a real video's
     audio track has: not already 16 kHz, not already mono);
  2. the macOS reference for that exact container — the same file decoded by
     ffmpeg to 16 kHz mono float32, which is precisely what
     `backend/core/video.py:extract_audio` does in production.

The device test then decodes (1) with MediaExtractor/MediaCodec and compares to
(2). Note what this does and does not isolate: both sides decode the SAME lossy
bitstream, so codec loss cancels and what remains is decoder-implementation
difference plus our own downmix/resample port. That is the question Gate E was
left with.

Output: core-scoring/src/test/resources/golden/device/ — picked up as androidTest
assets by :app (see app/build.gradle.kts), so nothing has to be pushed by hand.

Usage:  python3 scripts/capture_device_fixtures.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "NativeLingoAndroid/core-scoring/src/test/resources/golden"
OUT = GOLDEN / "device"
SR = 16000

# The golden clip every other fixture is built from, so the device numbers are
# comparable with the JVM ones (emb/ref_samantha.npy is its macOS embedding).
SOURCE_NPY = GOLDEN / "wav/ref_samantha.npy"

# Two containers, chosen for what they prove rather than for coverage:
#   mp4/AAC   — the overwhelmingly common case for `videos/` material.
#   webm/Opus — the format R-9's original plan claimed MediaCodec covered
#               incompletely. Opus decode has been mandatory since API 21, and
#               this is where that claim gets tested on an actual device.
VARIANTS = {
    "aac_44k1_stereo": dict(
        name="clip_aac.mp4",
        args=["-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2", "-f", "mp4"],
    ),
    "opus_48k_stereo": dict(
        name="clip_opus.webm",
        args=["-c:a", "libopus", "-b:a", "96k", "-ar", "48000", "-ac", "2", "-f", "webm"],
    ),
}


def run(cmd: list[str], stdin: bytes | None = None) -> bytes:
    p = subprocess.run(cmd, input=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        sys.exit(f"command failed: {' '.join(cmd)}\n{p.stderr.decode(errors='replace')[-2000:]}")
    return p.stdout


def main() -> None:
    if shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg not on PATH")
    if not SOURCE_NPY.is_file():
        sys.exit(f"missing {SOURCE_NPY} — run scripts/capture_golden.py first")

    src = np.load(SOURCE_NPY).astype(np.float32)
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"source: {SOURCE_NPY.name}  {src.size} samples @ {SR} Hz = {src.size / SR:.3f}s")

    manifest: dict[str, object] = {
        "producer": "scripts/capture_device_fixtures.py",
        "purpose": "device-side Gate E (R-9): platform decoder vs macOS ffmpeg, same container",
        "source": "golden/wav/ref_samantha.npy",
        "source_samples": int(src.size),
        "target_sr": SR,
        # R-9's own criteria, re-used verbatim rather than invented for the device.
        # The sample-domain number is reported, not gated: R-9's finding was that
        # sample-domain differences of ~40 dB SNR are invisible in the score.
        "criteria": {"emb_min_cosine": 0.995, "max_dtw_cost_delta": 0.005, "max_accuracy_delta": 0.5},
        # `emb_min_cosine` alone would misdescribe how the device asserts it, so the
        # manifest carries the disjunction too — a reader of the fixture should not
        # have to open the test to learn that a measured noise floor is part of the
        # criterion. Regenerating this file must not drop the note.
        "emb_cosine_note": (
            "0.995 was measured on the desktop with the fp32 encoder while swapping resampler "
            "kernels, so on device it is asserted as a disjunction: cos >= 0.995 OR "
            "cos >= controlCos - 0.002, where controlCos re-encodes the reference with only the "
            "measured gain/fractional-shift perturbation applied. Rationale: a quantised encoder "
            "is a step function, and R-5 measured the int8 export at 0.983-0.987 against fp32 on "
            "identical waveforms — demanding 0.995 across two decodes asks for more agreement "
            "than the encoder shows with itself across precisions. With the shipped fp16 encoder "
            "the bar is met outright (0.9998-0.99996 here, 0.9998 on the seek case), so the floor "
            "clause is currently a dormant fallback; it was the pass path on the int8 run it was "
            "written for (0.9888-0.9928). See AudioDecodeDeviceTest and "
            "docs/reviews/2026-07-26-android-device-first-run.md."
        ),
        "variants": {},
    }

    for key, v in VARIANTS.items():
        container = OUT / str(v["name"])
        # raw f32le on stdin → encoded container. `-y` because re-running the
        # script must be idempotent.
        run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "pipe:0",
             *v["args"], str(container)],
            stdin=src.tobytes(),
        )

        # The macOS reference: decode the container we just wrote, exactly as
        # video.py does (16 kHz mono f32le).
        raw = run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(container),
             "-ar", str(SR), "-ac", "1", "-f", "f32le", "pipe:1"]
        )
        ref = np.frombuffer(raw, dtype=np.float32)
        ref_path = OUT / f"{container.stem}_ffmpeg16k.npy"
        np.save(ref_path, ref)

        # Encoder delay/padding means the decoded length is NOT the source length;
        # recording it keeps the device test from asserting a wrong invariant.
        manifest["variants"][key] = {
            "container": container.name,
            "reference": ref_path.name,
            "container_bytes": container.stat().st_size,
            "reference_samples": int(ref.size),
            "delta_vs_source_samples": int(ref.size) - int(src.size),
        }
        print(
            f"  {container.name:16s} {container.stat().st_size:7d} B  ->  "
            f"{ref.size} samples ({ref.size - src.size:+d} vs source)"
        )

    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
