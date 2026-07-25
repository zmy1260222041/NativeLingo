#!/usr/bin/env python3
"""Capture macOS golden artifacts — the numerical-parity baseline for the
Android port (docs/android-migration.md §10).

Run on macOS (needs `say` + the runtime venv: torch/torchaudio/transformers)::

    .venv/bin/python scripts/capture_golden.py
    # or point elsewhere:
    .venv/bin/python scripts/capture_golden.py --out NativeLingoAndroid/core-scoring/src/test/resources/golden

Produces, under <out>/:
  manifest.json              corpus index, tolerances, provenance (device/git)
  wav/<name>.npy             16kHz mono float32 input waveforms (the fixtures)
  emb/<name>.npy             wav2vec2-base-960h layers 6-9 mean embedding (T,768)
                             —— Layer 2, Gate A (the existence proof)
  pair/<name>.json           {accuracy, fluency, rate, cost, path_len}
  pair/<name>_path.npy       DTW path (K,2)
  pair/<name>_costs.npy      per-step cosine costs (K,)
                             —— Layer 1, Gate A
  mms/<name>_emission.npy    MMS CTC emission (T,V)   [if torchaudio available]
  mms/<name>_spans.json      torchaudio aligner word spans (s)  —— Layer 2, Gate B
  espeak/<name>_emission.npy espeak CTC log-softmax (T,V)  [if model available]
  espeak/<name>_decode.txt   greedy IPA decode              —— Layer 2, Gate C

The Android `:core-scoring` JVM tests load these and assert parity within
tolerance (the tolerance is what captures int8 drift). macOS is the gold
standard source; this script is its dumper.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

# make `from backend.core...` importable when run from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.audio_io import load_audio, trim_silence  # noqa: E402
from backend.core.pipeline import analyze_arrays  # noqa: E402
from backend.core.ssl_encoder import SSLEncoder  # noqa: E402

TARGET_SR = 16000
SENTENCE = "The quick brown fox jumps over the lazy dog."
WRONG = "The slow purple cat sleeps under the busy table."

# --- tolerances mirrored in the Android golden tests (docs/android-migration.md §10) ---
TOL = {
    "dtw_cost": 0.02,
    "accuracy": 2.0,
    "fluency": 3.0,
    "word_status_exact": True,
    "align_frame": 1,          # ≤1 frame (20ms)
    "emb_min_cosine": 0.995,   # post-CMVN, per-frame
    "mms_min_cosine": 0.995,
    "espeak_decode_exact": True,
}

SAY = shutil.which("say")


def synth(text: str, voice: str, rate: int, dst: str) -> str:
    subprocess.run(
        [SAY, "-v", voice, "-r", str(rate), "-o", dst, text],
        check=True,
        capture_output=True,
    )
    return dst


# (name, text, voice, rate, trim?) — trim matches analyze_arrays' contract
CORPUS = [
    ("ref_samantha", SENTENCE, "Samantha", 175, True),
    ("crossvoice_daniel", SENTENCE, "Daniel", 175, True),
    ("wrongtext_samantha", WRONG, "Samantha", 175, True),
    ("slow_samantha", SENTENCE, "Samantha", 80, True),
    # untrimmed variant: phoneme CTC needs real leading/trailing silence
    ("ref_samantha_raw", SENTENCE, "Samantha", 175, False),
]


def build_corpus(tmp: str) -> dict[str, np.ndarray]:
    """Synthesize the controlled corpus with macOS `say`."""
    if SAY is None:
        sys.exit("ERROR: macOS `say` not available — run on macOS.")
    out = {}
    for name, text, voice, rate, do_trim in CORPUS:
        aiff = os.path.join(tmp, f"{name}.aiff")
        synth(text, voice, rate, aiff)
        wav = load_audio(aiff)
        if do_trim:
            wav = trim_silence(wav)
        out[name] = wav
        print(f"  synth {name}: {len(wav)} samples ({len(wav)/TARGET_SR:.2f}s)")
    return out


def dump_embeddings(encoder: SSLEncoder, corpus: dict[str, np.ndarray], out_dir: str):
    emb_dir = os.path.join(out_dir, "emb")
    os.makedirs(emb_dir, exist_ok=True)
    wav_dir = os.path.join(out_dir, "wav")
    os.makedirs(wav_dir, exist_ok=True)
    for name, wav in corpus.items():
        np.save(os.path.join(wav_dir, f"{name}.npy"), wav)
        # the wav2vec2 feature-extractor NORMALISED input (what the ONNX model
        # consumes) — lets the core-embed test isolate the ONNX run from the
        # Kotlin normalization port.
        inputs = encoder.extractor(wav, sampling_rate=TARGET_SR, return_tensors="pt")
        np.save(os.path.join(wav_dir, f"{name}_input.npy"), inputs.input_values.numpy())
        emb = encoder.encode(wav)
        np.save(os.path.join(emb_dir, f"{name}.npy"), emb)
        print(f"  emb {name}: {emb.shape}")


def dump_pairs(encoder, corpus, out_dir):
    """Layer 1 scoring golden for the key pairs (esp. speaker invariance)."""
    pair_dir = os.path.join(out_dir, "pair")
    os.makedirs(pair_dir, exist_ok=True)
    # (pair_name, ref_key, learner_key)
    pairs = [
        ("samevoice", "ref_samantha", "ref_samantha"),
        ("speakervariance", "ref_samantha", "crossvoice_daniel"),
        ("wrongtext", "ref_samantha", "wrongtext_samantha"),
        ("slow", "ref_samantha", "slow_samantha"),
    ]
    for pname, ref_k, lrn_k in pairs:
        # analyze_arrays assumes pre-trimmed inputs; corpus entries are trimmed.
        res = analyze_arrays(corpus[ref_k], corpus[lrn_k])
        meta = {
            "accuracy": res.accuracy,
            "fluency": res.fluency,
            "speech_rate_ratio": res.speech_rate_ratio,
            "raw_path_cost": res.raw_path_cost,
            "problems": [
                {"ref_start_s": p.ref_start_s, "ref_end_s": p.ref_end_s,
                 "severity": p.severity, "kind": p.kind}
                for p in res.problems
            ],
        }
        with open(os.path.join(pair_dir, f"{pname}.json"), "w") as f:
            json.dump(meta, f, indent=2)
        print(f"  pair {pname}: acc={res.accuracy} flu={res.fluency} cost={res.raw_path_cost}")


def dump_paths(encoder, corpus, out_dir):
    """Dump the raw DTW path + per-step costs (Gate A truth), the fluency inputs,
    and the per-word detail projection (FR-6) for each pair."""
    from backend.core.speaker_norm import normalize_pair
    from backend.core.align import dtw_align
    from backend.core.prosody import extract_prosody
    from backend.core.detail import compute_word_details
    from backend.core import forced_align as fa

    pair_dir = os.path.join(out_dir, "pair")
    pairs = [
        ("samevoice", "ref_samantha", "ref_samantha"),
        ("speakervariance", "ref_samantha", "crossvoice_daniel"),
        ("wrongtext", "ref_samantha", "wrongtext_samantha"),
        ("slow", "ref_samantha", "slow_samantha"),
    ]

    # reference word boundaries (clip-relative seconds) via MMS — same for every
    # pair (reference is always ref_samantha, already trimmed).
    ref_words: list[dict] = []
    if fa.is_available():
        names = SENTENCE.rstrip(".").split()
        spans = fa.align_words(names, corpus["ref_samantha"])
        if spans:
            ref_words = [
                {"word": w, "start": sp[0], "end": sp[1]}
                for w, sp in zip(names, spans) if sp
            ]

    for pname, ref_k, lrn_k in pairs:
        ref_emb = encoder.encode(corpus[ref_k])
        lrn_emb = encoder.encode(corpus[lrn_k])
        ref_n, lrn_n = normalize_pair(ref_emb, lrn_emb)
        dtw = dtw_align(ref_n, lrn_n)
        np.save(os.path.join(pair_dir, f"{pname}_path.npy"), dtw.path)
        np.save(os.path.join(pair_dir, f"{pname}_costs.npy"), dtw.path_costs)

        # fluency inputs (Gate A · Layer 1): prosody pause features + lengths.
        prosody = extract_prosody(corpus[lrn_k])
        dur = max(prosody.duration_s, 1e-3)
        with open(os.path.join(pair_dir, f"{pname}_fluency.json"), "w") as f:
            json.dump({
                "ref_len": int(ref_emb.shape[0]),
                "learner_len": int(lrn_emb.shape[0]),
                "pause_per_s": prosody.num_pauses / dur,
                "pause_ratio": prosody.total_pause_s / dur,
            }, f, indent=2)

        # per-word detail (FR-6): project DTW path onto the reference word grid.
        if ref_words:
            details = compute_word_details(dtw, ref_words)
            with open(os.path.join(pair_dir, f"{pname}_detail.json"), "w") as f:
                json.dump({
                    "words": [
                        {"word": d.word, "start": d.start, "end": d.end,
                         "accuracy": d.accuracy, "status": d.status}
                        for d in details
                    ],
                }, f, indent=2)
            print(f"  detail {pname}: {len(details)} words")


def dump_mms(corpus, out_dir):
    """Layer 2 (Gate B): MMS CTC emission + torchaudio aligner word spans."""
    try:
        from backend.core import forced_align as fa
    except Exception as e:  # noqa: BLE001
        print(f"  mms: SKIP (forced_align import failed: {e})")
        return False
    if not fa.is_available():
        print("  mms: SKIP (torchaudio/MMS_FA unavailable)")
        return False
    import torch  # noqa: F401

    mms_dir = os.path.join(out_dir, "mms")
    os.makedirs(mms_dir, exist_ok=True)
    model, tokenizer, aligner = fa._get_state()

    # use the reference sentence; align its words to demonstrate word spans
    name = "ref_samantha"
    wav = corpus[name]
    words = SENTENCE.rstrip(".").split()
    cleaned = [fa._clean(w) for w in words]
    keep_idx = [i for i, c in enumerate(cleaned) if c]
    t = torch.from_numpy(np.asarray(wav, dtype="float32")).unsqueeze(0)
    with torch.inference_mode():
        emission, _ = model(t)
    em = emission[0].cpu().numpy()           # (T, V)
    nframes = em.shape[0]
    spf = (wav.size / TARGET_SR) / nframes
    spans = aligner(emission[0], tokenizer([cleaned[i] for i in keep_idx]))
    np.save(os.path.join(mms_dir, f"{name}_emission.npy"), em)
    word_spans = []
    # flat per-char ground truth so the Android CtcViterbi port can be checked
    # frame-accurately against torchaudio's aligner (Gate B / R-6).
    char_tokens = []
    for k, gi in enumerate(keep_idx):
        cs = spans[k] if k < len(spans) else None
        if not cs:
            word_spans.append({"word": words[gi], "start": None, "end": None})
            continue
        cleaned_word = cleaned[gi]
        f0, f1 = int(cs[0].start), int(cs[-1].end)
        word_spans.append({
            "word": words[gi],
            "start": round(f0 * spf, 4),
            "end": round((f1 + 1) * spf, 4),
        })
        # spans[k] is one TokenSpan per character of the cleaned word, in order
        for ci, ts in enumerate(cs):
            char_tokens.append({
                "word": words[gi],
                "char": cleaned_word[ci] if ci < len(cleaned_word) else "?",
                "token_id": int(ts.token),
                "start_frame": int(ts.start),
                "end_frame": int(ts.end),
            })
    with open(os.path.join(mms_dir, f"{name}_spans.json"), "w") as f:
        json.dump({"spf": spf, "nframes": nframes, "blank": 0,
                   "spans": word_spans, "char_tokens": char_tokens}, f, indent=2)
    print(f"  mms {name}: emission {em.shape}, {len(word_spans)} words, {len(char_tokens)} chars")
    return True


def dump_espeak(corpus, out_dir):
    """Layer 2 (Gate C): espeak CTC emission + greedy IPA decode."""
    try:
        from backend.core import phoneme as ph
        if not ph.is_available():
            print("  espeak: SKIP (model unavailable)")
            return False
    except Exception as e:  # noqa: BLE001
        print(f"  espeak: SKIP (import failed: {e})")
        return False

    es_dir = os.path.join(out_dir, "espeak")
    os.makedirs(es_dir, exist_ok=True)
    # dump emissions/decodes for the raw (untrimmed) reference span and a
    # couple of word-level slices — Gate C verifies the espeak int8 model
    # reproduces these emissions / greedy decode within tolerance.
    name = "ref_samantha_raw"
    wav = corpus[name]
    em = ph._emissions(wav)
    dec = ph.decode_phonemes(wav)
    np.save(os.path.join(es_dir, f"{name}_emission.npy"), em)
    with open(os.path.join(es_dir, f"{name}_decode.txt"), "w") as f:
        f.write(dec)
    print(f"  espeak {name}: emission {em.shape}, decode='{dec}'")
    return True


def git_provenance() -> dict:
    rev = "(unknown)"
    try:
        rev = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:  # noqa: BLE001
        pass
    return {"git_head": rev, "sentence": SENTENCE}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out", default="NativeLingoAndroid/core-scoring/src/test/resources/golden",
        help="output directory for golden artifacts",
    )
    args = ap.parse_args()
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)

    print(f"== capturing golden → {out_dir} ==")
    with tempfile.TemporaryDirectory() as tmp:
        corpus = build_corpus(tmp)

        print("-- wav2vec2 embeddings (Layer 2 / Gate A) --")
        encoder = SSLEncoder()  # default device (MPS on macOS = production path)
        dump_embeddings(encoder, corpus, out_dir)

        print("-- scoring pairs (Layer 1 / Gate A) --")
        dump_pairs(encoder, corpus, out_dir)
        dump_paths(encoder, corpus, out_dir)

        print("-- MMS forced alignment (Layer 2 / Gate B) --")
        mms_ok = dump_mms(corpus, out_dir)

        print("-- espeak phoneme CTC (Layer 2 / Gate C) --")
        espeak_ok = dump_espeak(corpus, out_dir)

    manifest = {
        "producer": "scripts/capture_golden.py (macOS gold-standard source)",
        "doc": "docs/android-migration.md",
        "provenance": git_provenance(),
        "corpus": [{"name": n, "text": t, "voice": v, "rate": r, "trimmed": tr}
                   for (n, t, v, r, tr) in CORPUS],
        "tolerances": TOL,
        "sections": {
            "emb": True, "pair": True, "mms": mms_ok, "espeak": espeak_ok,
        },
        "notes": [
            "Embeddings are wav2vec2-base-960h transformer layers 6-9 mean "
            "(ssl_encoder.DEFAULT_LAYERS), pre-CMVN. Apply CMVN in-test before "
            "comparing cosine >= emb_min_cosine.",
            "DTW path/costs are the raw banded-DTW output (align.dtw_align, "
            "band_frac=0.2) on CMVN-normalised embeddings.",
            "MMS spans come from torchaudio's get_aligner(); the Android "
            "CtcViterbi.kt port must reproduce them within align_frame.",
            "espeak decode is CTC greedy on the raw reference span; int8 must "
            "match the greedy string exactly on clean references.",
        ],
    }
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"== done. manifest at {os.path.join(out_dir, 'manifest.json')} ==")


if __name__ == "__main__":
    main()
