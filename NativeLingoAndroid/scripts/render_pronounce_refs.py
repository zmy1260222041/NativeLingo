#!/usr/bin/env python3
"""Render offline pronunciation reference clips for the Android Memorizing module.

Why this exists: sherpa-onnx 1.13.4's OfflineTts crashes on the second generate()
in an arm64 process (native SIGSEGV, issue #3675 class), so the app cannot use
runtime Piper TTS. Instead we render the curated label vocabulary ONCE, here,
with the exact desktop Piper voice (noise_scale=0, noise_w_scale=0) and ship the
16 kHz mono PCM16 wavs as assets. The app reads a wav when the user taps "play
reference" — zero native TTS, unlimited replays, and the bytes the user hears are
bit-identical to what the scorer compares against (the determinism contract).

Vocabulary source: the same label JSONs :core-vision ships, so every label that
can ever appear on a hotspot has a reference clip. Labels are deduped by their
English form.

Output: models/pronounce-refs/<slug>.wav — slug is the lowercased, hyphen-joined
label (e.g. "coffee mug" -> "coffee-mug.wav"). 16 kHz mono PCM16, matching the
SSL encoder's input rate so no resampling is needed at score time.

Run from the repo root with the desktop .venv:
    .venv/bin/python NativeLingoAndroid/scripts/render_pronounce_refs.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import soundfile as sf

REPO = Path(__file__).resolve().parents[2]  # NativeLingo repo root
LABEL_DIR = REPO / "NativeLingoAndroid" / "core-vision" / "src" / "main" / "resources" / "com" / "nativelingo" / "vision" / "labels"
OUT_DIR = REPO / "models" / "pronounce-refs"


def collect_labels() -> list[str]:
    """Every curated English label that can reach the UI, deduped, sorted."""
    labels: set[str] = set()

    coco_en = (LABEL_DIR / "coco_names.txt").read_text(encoding="utf-8").splitlines()
    for line in coco_en:
        line = line.strip()
        if line and line != "person":
            labels.add(line)

    everyday = json.loads((LABEL_DIR / "yoloe_everyday_labels.json").read_text(encoding="utf-8"))
    for category in everyday["categories"].values():
        labels.update(category.keys())

    overrides = json.loads((LABEL_DIR / "yoloe_labels.json").read_text(encoding="utf-8"))
    labels.update(overrides["labels"].keys())

    return sorted(labels)


def slugify(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "unknown"


def main() -> None:
    # Defer the piper import so `--help` and the label scan don't require the
    # desktop venv.
    from piper import PiperVoice, SynthesisConfig  # type: ignore
    import piper as piper_pkg  # type: ignore
    import numpy as np
    import librosa

    # Resolve the model + espeak-ng-data from LOCAL caches (no snapshot_download —
    # that re-validates the entire multi-GB piper-voices repo). The model lives in
    # the HF hub cache from a prior desktop run; espeak-ng-data ships inside the
    # piper package itself.
    hf_cache = Path.home() / ".cache/huggingface/hub/models--rhasspy--piper-voices/snapshots"
    model_path = next(hf_cache.rglob("en_US-libritts_r-medium.onnx"))
    espeak_dir = Path(piper_pkg.__file__).parent / "espeak-ng-data"
    assert model_path.is_file(), f"piper model missing at {model_path}"
    assert espeak_dir.is_dir(), f"espeak-ng-data missing at {espeak_dir}"
    print(f"model: {model_path}\nespeak: {espeak_dir}")

    voice = PiperVoice.load(str(model_path), espeak_data_dir=str(espeak_dir))
    config = SynthesisConfig(noise_scale=0.0, noise_w_scale=0.0)  # deterministic
    native_rate = voice.config.sample_rate  # libritts_r-medium = 22050

    labels = collect_labels()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"rendering {len(labels)} reference clips @ {native_rate} Hz → {OUT_DIR}", flush=True)

    skipped = 0
    rendered = 0
    for i, label in enumerate(labels, 1):
        slug = slugify(label)
        out = OUT_DIR / f"{slug}.wav"
        if out.exists():
            rendered += 1
            continue  # idempotent re-run
        try:
            chunks = list(voice.synthesize(label, syn_config=config))
            audio = np.concatenate([c.audio_float_array for c in chunks]) if chunks else np.zeros(0, dtype=np.float32)
            if audio.size == 0:
                skipped += 1
                continue
            # Resample native → 16 kHz mono PCM16 to match the SSL encoder input
            # (no runtime resample needed on device).
            audio16 = librosa.resample(audio.astype(np.float32), orig_sr=native_rate, target_sr=16000)
            sf.write(str(out), audio16, 16000, subtype="PCM_16", format="WAV")
            rendered += 1
        except Exception as exc:  # noqa: BLE001
            skipped += 1
            print(f"  [{i}/{len(labels)}] SKIP ({exc}) {label!r}")
            continue
        if i % 25 == 0:
            print(f"  [{i}/{len(labels)}] rendered {label!r}", flush=True)

    total_bytes = sum(p.stat().st_size for p in OUT_DIR.glob("*.wav"))
    print(f"done: {rendered} clips rendered, {skipped} skipped, "
          f"{total_bytes / 1e6:.1f} MB in {OUT_DIR}")


if __name__ == "__main__":
    main()
