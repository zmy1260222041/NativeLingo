"""Quantify the real-voice vs TTS reference gap (PRD NFR-Q1, review R-1 step 1).

v1.2's score calibration was fitted with `say`-synthesised references, but the
product's references are real human voices from web videos (news broadcasts —
FR-M1). This script measures how big that domain shift actually is, in the
units the calibrator consumes:

* gap ε = DTW cost(real_human_read(X), say_synth(X)) over many texts X.
  Interpretation: a *perfect* learner imitation of a real reference would
  present cost ≈ ε to a TTS-fitted calibrator, so `isotonic(ε)` is the score
  ceiling a real-reference setup can reach. If that ceiling stays in the 90s,
  no correction is warranted; if it sags, we correct (offset or refit).
* speaking-rate shift = duration(say X) / duration(real X). The fluency GAM's
  dominant feature is |log(learner/ref rate)|, so a systematic real-vs-TTS
  pace difference skews fluency scores by that ratio.

Sources: LibriSpeech (clean, many speakers, read speech) + the in-app news
video (7.1.mp4 — the actual product domain).

Usage: .venv/bin/python -m scripts.quantify_ref_gap [--n 300]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess

import numpy as np

from backend.core.audio_io import TARGET_SR, load_audio, trim_silence
from backend.core.ssl_encoder import SSLEncoder
from backend.core.speaker_norm import normalize_pair
from backend.core.align import dtw_align
from backend.core.score_b import load_calibration, accuracy_from_cost

SAY = shutil.which("say")
REF_VOICE = os.environ.get("NL_REF_VOICE", "Samantha")
REF_RATE = os.environ.get("NL_REF_RATE", "175")
CACHE_DIR = os.environ.get("NL_REF_CACHE", "data/ref_tts_cache")
VIDEO = "videos/7.1.mp4"
SENTS = "videos/7.1.sentences.json"


def synth(text: str) -> np.ndarray | None:
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
    return load_audio(path)


def pair_stats(encoder, real_wav, tts_wav):
    real_t, tts_t = trim_silence(real_wav), trim_silence(tts_wav)
    if real_t.size < TARGET_SR // 2 or tts_t.size < TARGET_SR // 2:
        return None
    re_ = encoder.encode(real_t)
    te = encoder.encode(tts_t)
    rn, tn = normalize_pair(re_, te)
    cost = dtw_align(rn, tn).normalized_cost
    # speaking-rate shift: how much faster/slower real speech is vs the TTS
    # reading of the same text (>1 = real is faster than TTS)
    rate_shift = (len(tts_t) / TARGET_SR) / max(len(real_t) / TARGET_SR, 1e-3)
    return float(cost), float(rate_shift)


def librispeech_items(n: int):
    """Load from a locally extracted LibriSpeech tree (dev-clean)."""
    import glob
    import soundfile as sf

    root = os.environ.get("NL_LIBRISPEECH", "data/librispeech/LibriSpeech/dev-clean")
    out = []
    for trans in sorted(glob.glob(os.path.join(root, "*", "*", "*.trans.txt"))):
        if len(out) >= n:
            break
        for line in open(trans):
            if len(out) >= n:
                break
            utt, text = line.strip().split(" ", 1)
            words = text.split()
            if not (4 <= len(words) <= 25):  # keep utterances sentence-like
                continue
            flac = os.path.join(os.path.dirname(trans), utt + ".flac")
            if not os.path.exists(flac):
                continue
            wav, sr = sf.read(flac, dtype="float32")
            if sr != TARGET_SR:
                continue
            out.append((text.capitalize() + ".", wav))
    return out


def news_items(max_n: int = 80):
    from backend.core.video import extract_audio

    sents = json.load(open(SENTS))
    if isinstance(sents, dict):
        sents = sents["sentences"]
    out = []
    for s in sents:
        if len(out) >= max_n:
            break
        dur = s["end"] - s["start"]
        words = len(s["text"].split())
        if not (2.0 <= dur <= 10.0 and 5 <= words <= 30):
            continue
        wav = extract_audio(VIDEO, s["start"], s["end"])
        out.append((s["text"], np.asarray(wav, dtype="float32")))
    return out


def report(name: str, costs: list[float], rates: list[float]) -> None:
    c, r = np.array(costs), np.array(rates)
    calib = load_calibration() is not None
    ceilings = [accuracy_from_cost(float(x)) for x in np.percentile(c, [50, 90])]
    print(f"\n== {name} ({len(c)} pairs) ==")
    print(f"  gap ε cost:  mean {c.mean():.3f}  median {np.median(c):.3f}  "
          f"p90 {np.percentile(c, 90):.3f}  std {c.std():.3f}")
    if calib:
        print(f"  perfect-imitation score ceiling: "
              f"median ε → {ceilings[0]:.1f}   p90 ε → {ceilings[1]:.1f}")
    print(f"  rate shift (tts_dur/real_dur): mean {r.mean():.3f}  "
          f"median {np.median(r):.3f}  p10 {np.percentile(r, 10):.3f}  "
          f"p90 {np.percentile(r, 90):.3f}")
    # what the rate shift does to the fluency GAM's dominant feature
    print(f"  |log rate shift| median {abs(np.log(r)).mean():.3f} "
          f"(adds ~this much to the learner's |log rate ratio| feature)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--source", choices=["news", "librispeech", "both"],
                    default="both")
    args = ap.parse_args()
    assert SAY, "macOS `say` required"

    encoder = SSLEncoder()

    arms = []
    if args.source in ("librispeech", "both"):
        arms.append(("LibriSpeech dev-clean (read speech, multi-speaker)",
                     librispeech_items(args.n)))
    if args.source in ("news", "both"):
        arms.append(("News video 7.1.mp4 (product domain)", news_items()))

    for name, items in arms:
        costs, rates = [], []
        for i, (text, real_wav) in enumerate(items):
            tts_wav = synth(text)
            if tts_wav is None:
                continue
            st = pair_stats(encoder, real_wav, tts_wav)
            if st is None:
                continue
            costs.append(st[0])
            rates.append(st[1])
            if (i + 1) % 50 == 0:
                print(f"[{name}] {i + 1}/{len(items)}", flush=True)
        report(name, costs, rates)


if __name__ == "__main__":
    main()
