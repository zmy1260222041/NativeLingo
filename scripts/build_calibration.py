"""Build the calibration feature set from speechocean762 (v1.2).

speechocean762 gives (learner_audio, text, human accuracy/fluency 0-10) but no
native reference audio — so we synthesise one per text with macOS `say`
(cached; texts repeat across speakers). For each utterance we run the exact
Track B path (encode -> CMVN -> DTW) and record the raw signals alongside the
human scores. A separate script (fit_calibrator.py) turns this into the
shipped calibration table.

Usage:
    .venv/bin/python -m scripts.build_calibration --n 1200 --split test \
        --layers 4 5 6 7 8 --out data/calibration_features.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

import numpy as np

from backend.core.audio_io import TARGET_SR, trim_silence
from backend.core.ssl_encoder import SSLEncoder
from backend.core.speaker_norm import normalize_pair
from backend.core.align import dtw_align
from backend.core.prosody import extract_prosody

SAY = shutil.which("say")
REF_VOICE = os.environ.get("NL_REF_VOICE", "Samantha")
REF_RATE = os.environ.get("NL_REF_RATE", "175")
CACHE_DIR = os.environ.get("NL_REF_CACHE", "data/ref_tts_cache")


def synth_ref(text: str) -> np.ndarray | None:
    """Synthesise the reference reading of ``text`` (cached on disk)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = abs(hash((text.strip(), REF_VOICE, REF_RATE)))
    path = os.path.join(CACHE_DIR, f"{key}.aiff")
    if not os.path.exists(path):
        r = subprocess.run(
            [SAY, "-v", REF_VOICE, "-r", REF_RATE, "-o", path, text],
            capture_output=True,
        )
        if r.returncode != 0:
            return None
    from backend.core.audio_io import load_audio

    return load_audio(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1200)
    ap.add_argument("--split", default="test")
    ap.add_argument("--layers", type=int, nargs="*", default=[4, 5, 6, 7, 8])
    ap.add_argument("--out", default="data/calibration_features.jsonl")
    args = ap.parse_args()

    if SAY is None:
        sys.exit("macOS `say` required for reference synthesis")

    from datasets import load_dataset

    ds = load_dataset("mispeech/speechocean762")[args.split]
    # stratified-ish: take every k-th row so scores/speakers stay mixed
    k = max(1, len(ds) // args.n)
    idxs = list(range(0, len(ds), k))[: args.n]

    encoder = SSLEncoder(layers=tuple(args.layers) if args.layers else None)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    n_done = 0
    with open(args.out, "w") as fout:
        for i, idx in enumerate(idxs):
            ex = ds[idx]
            try:
                learner = np.asarray(ex["audio"]["array"], dtype="float32")
                if ex["audio"]["sampling_rate"] != TARGET_SR:
                    continue
                text = ex["text"].strip().capitalize() + "."
                ref = synth_ref(text)
                if ref is None:
                    continue
                learner_t = trim_silence(learner)
                ref_t = trim_silence(ref)
                if learner_t.size < TARGET_SR // 4 or ref_t.size < TARGET_SR // 4:
                    continue

                re_ = encoder.encode(ref_t)
                le = encoder.encode(learner_t)
                rn, ln = normalize_pair(re_, le)
                dtw = dtw_align(rn, ln)

                path = dtw.path
                ratio = le.shape[0] / max(re_.shape[0], 1)
                if path.shape[0]:
                    ideal = path[:, 0].astype("float64") * ratio
                    norm_dev = float(
                        np.abs(path[:, 1] - ideal).mean() / max(le.shape[0], 1)
                    )
                else:
                    norm_dev = 1.0

                pros = extract_prosody(learner_t)
                dur = max(pros.duration_s, 1e-3)
                rec = {
                    "idx": int(idx),
                    "text": ex["text"],
                    "cost": round(float(dtw.normalized_cost), 5),
                    "path_dev": round(norm_dev, 5),
                    "rate_ratio": round(float(ratio), 4),
                    "pause_per_s": round(pros.num_pauses / dur, 3),
                    "pause_ratio": round(pros.total_pause_s / dur, 4),
                    "artic_rate": pros.articulation_rate,
                    "human_accuracy": ex["accuracy"],
                    "human_fluency": ex["fluency"],
                    "human_total": ex["total"],
                }
                fout.write(json.dumps(rec) + "\n")
                fout.flush()
                n_done += 1
                if n_done % 50 == 0:
                    print(f"[{n_done}/{len(idxs)}] idx={idx} cost={rec['cost']}",
                          flush=True)
            except Exception as e:  # noqa: BLE001 - skip bad rows, keep going
                print(f"skip idx={idx}: {e}", flush=True)
    print(f"done: {n_done} rows -> {args.out}")


if __name__ == "__main__":
    main()
