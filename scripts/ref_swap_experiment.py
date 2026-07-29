"""Reference-swap experiment (PRD NFR-Q1, review R-1 — decisive arm).

`quantify_ref_gap.py` measures cost(real, TTS) = ε, but that alone doesn't say
which direction calibrated scores drift when the product swaps TTS references
(c Calibration time) for real human references (FR-M1, product time). A real
learner shares "real human channel" factors with a real reference, so real
refs could just as well *raise* scores.

CMU ARCTIC has multiple native speakers reading the SAME 1132 sentences, which
enables the decisive comparison for a *good* reader:

    score under real ref : isotonic(cost(native_A(X), native_B(X)))
    score under TTS ref  : isotonic(cost(say(X),      native_B(X)))

If real-ref scores come out >= TTS-ref scores, no correction is needed (the
measured ε is mostly "voice gap" that a good real reader doesn't pay).

Usage: .venv/bin/python -m scripts.ref_swap_experiment [--n 250]
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

import numpy as np

# `backend/` now lives under desktop/ (not the repo root).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "desktop"))

from backend.core.audio_io import TARGET_SR, load_audio, trim_silence
from backend.core.ssl_encoder import SSLEncoder
from backend.core.speaker_norm import normalize_pair
from backend.core.align import dtw_align
from backend.core.score_b import accuracy_from_cost

SAY = shutil.which("say")
REF_VOICE = os.environ.get("NL_REF_VOICE", "Samantha")
REF_RATE = os.environ.get("NL_REF_RATE", "175")
CACHE_DIR = os.environ.get("NL_REF_CACHE", "data/ref_tts_cache")
DATASET = "MikhailT/cmu-arctic"
REF_SPK = "slt"           # female native — plays the product's real reference
LEARNER_SPKS = ["bdl", "clb"]  # male / female natives — play "good readers"


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


def _norm_text(text: str) -> str:
    """Speaker-dataset-agnostic key: letters/digits/spaces only, lowercase."""
    import re

    return re.sub(r"[^a-z0-9 ]", "", " ".join(text.split()).lower())


def load_speaker(spk: str, n: int) -> dict[str, np.ndarray]:
    """Return {normalised_text: wav} for one ARCTIC speaker."""
    from datasets import load_dataset

    ds = load_dataset(DATASET, split=spk)
    out: dict[str, np.ndarray] = {}
    for ex in ds:
        if len(out) >= n:
            break
        text = _norm_text(ex["text"])
        words = text.split()
        if not (5 <= len(words) <= 25):
            continue
        out[text] = np.asarray(ex["audio"]["array"], dtype="float32")
    return out


def cost_of(encoder, a: np.ndarray, b: np.ndarray) -> float | None:
    a, b = trim_silence(a), trim_silence(b)
    if a.size < TARGET_SR // 2 or b.size < TARGET_SR // 2:
        return None
    ea, eb = encoder.encode(a), encoder.encode(b)
    ea, eb = normalize_pair(ea, eb)
    return float(dtw_align(ea, eb).normalized_cost)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=250)
    ap.add_argument("--l2", action="store_true",
                    help="also run the L2-learner arm (boldvoice/l2_arctic)")
    args = ap.parse_args()
    assert SAY, "macOS `say` required"

    encoder = SSLEncoder()
    ref = load_speaker(REF_SPK, args.n)
    learners = {s: load_speaker(s, args.n) for s in LEARNER_SPKS}

    rows = []
    for text, ref_wav in ref.items():
        tts = synth(text)
        if tts is None:
            continue
        row = {"eps": cost_of(encoder, ref_wav, tts)}  # cost(real_ref, TTS)
        for spk, table in learners.items():
            lw = table.get(text)
            if lw is None:
                continue
            row[f"real_{spk}"] = cost_of(encoder, ref_wav, lw)   # real ref
            row[f"tts_{spk}"] = cost_of(encoder, tts, lw)        # TTS ref
        rows.append(row)
        if len(rows) % 50 == 0:
            print(f"[{len(rows)}]", flush=True)

    print(f"\n{len(rows)} shared utterances (ref={REF_SPK})")
    eps = np.array([r["eps"] for r in rows if r["eps"] is not None])
    print(f"cost(real_ref, TTS) ε:            mean {eps.mean():.3f}  "
          f"median {np.median(eps):.3f}")
    for spk in LEARNER_SPKS:
        real = np.array([r[f"real_{spk}"] for r in rows
                         if r.get(f"real_{spk}") is not None])
        tts = np.array([r[f"tts_{spk}"] for r in rows
                        if r.get(f"tts_{spk}") is not None])
        s_real = np.array([accuracy_from_cost(c) for c in real])
        s_tts = np.array([accuracy_from_cost(c) for c in tts])
        print(f"\nlearner {spk}: cost real-ref {real.mean():.3f} vs "
              f"tts-ref {tts.mean():.3f}  (Δ {real.mean() - tts.mean():+.3f})")
        print(f"  calibrated score: real-ref {s_real.mean():.1f} "
              f"(p10 {np.percentile(s_real, 10):.1f}) vs "
              f"tts-ref {s_tts.mean():.1f} (p10 {np.percentile(s_tts, 10):.1f})")

    if args.l2:
        # full ref table so L2 utterances (spread over all 1132 prompts) match
        run_l2_arm(encoder, load_speaker(REF_SPK, 1200))


L2_DATASET = "boldvoice/l2_arctic"
L2_SR = 16000  # boldvoice mirror is 16 kHz (verified by alignment cost)
L2_SPKS = ["ABA", "SKA", "YBAA", "TNI", "ZHAA", "HQTV"]  # varied L1s
L2_PER_SPK = 25


def run_l2_arm(encoder, ref_table: dict[str, np.ndarray]) -> None:
    """Same swap, but the 'learners' are real L2 speakers (the actual user
    population) reading the same ARCTIC sentences as the native reference."""
    from collections import defaultdict

    from datasets import load_dataset

    from backend.core.audio_io import load_audio_from_array

    wanted = {s: L2_PER_SPK for s in L2_SPKS}
    samples: dict[str, list[tuple[str, np.ndarray]]] = defaultdict(list)
    ds = load_dataset(L2_DATASET, split="train", streaming=True)
    for ex in ds:
        spk = ex["speaker"]
        if spk not in wanted or wanted[spk] <= 0:
            continue
        text = _norm_text(ex["text"])
        if text not in ref_table:
            continue
        wav = load_audio_from_array(
            np.asarray(ex["waveform"], dtype="float32"), L2_SR
        )
        samples[spk].append((text, wav))
        wanted[spk] -= 1
        if all(v <= 0 for v in wanted.values()):
            break

    print(f"\n--- L2 arm (real L2 learners, ref={REF_SPK}) ---")
    for spk, items in samples.items():
        real_costs, tts_costs = [], []
        for text, wav in items:
            tts = synth(text)
            if tts is None:
                continue
            cr = cost_of(encoder, ref_table[text], wav)
            ct = cost_of(encoder, tts, wav)
            if cr is None or ct is None:
                continue
            real_costs.append(cr)
            tts_costs.append(ct)
        if not real_costs:
            continue
        real, tts = np.array(real_costs), np.array(tts_costs)
        s_real = np.array([accuracy_from_cost(c) for c in real])
        s_tts = np.array([accuracy_from_cost(c) for c in tts])
        print(f"{spk} ({len(real)} utt): cost real {real.mean():.3f} vs "
              f"tts {tts.mean():.3f} (Δ {real.mean() - tts.mean():+.3f}) | "
              f"score real {s_real.mean():.1f} vs tts {s_tts.mean():.1f}")


if __name__ == "__main__":
    main()
