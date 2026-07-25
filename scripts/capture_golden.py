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
import glob
import json
import math
import os
import re
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
    the per-word/per-sentence detail projection (FR-6), the Track-B problem
    regions (FR-4) and the rule-engine feedback payload (FR-9) for each pair."""
    from backend.core.speaker_norm import normalize_pair
    from backend.core.align import dtw_align
    from backend.core.prosody import extract_prosody, compare_prosody
    from backend.core.detail import compute_word_details, compute_sentence_details
    from backend.core.score_b import score_track_b
    from backend.core.feedback import generate_feedback
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

            # sentence-level detail (FR-6): one sentence spanning all words, with
            # the learner span shifted by a non-zero offset so the Kotlin port's
            # offset handling is actually exercised (macOS passes the trim offset).
            sentence = {
                "index": 0, "text": SENTENCE,
                "start": ref_words[0]["start"], "end": ref_words[-1]["end"],
                "words": ref_words,
            }
            LEARNER_OFFSET = 0.137
            sdetails = compute_sentence_details(dtw, [sentence],
                                                learner_offset=LEARNER_OFFSET)
            with open(os.path.join(pair_dir, f"{pname}_sentence.json"), "w") as f:
                json.dump({
                    "learner_offset": LEARNER_OFFSET,
                    "sentences": [
                        {"index": s.index, "text": s.text, "start": s.start,
                         "end": s.end, "accuracy": s.accuracy, "fluency": s.fluency,
                         "learner_start": s.learner_start, "learner_end": s.learner_end}
                        for s in sdetails
                    ],
                }, f, indent=2)

        # Track-B result + problem regions (FR-4) and the feedback payload (FR-9).
        # Both are deterministic functions of the DTW result + prosody, so the
        # Kotlin ports can be asserted exactly (regions) / by tip-set (feedback).
        pps = prosody.num_pauses / dur
        pr = prosody.total_pause_s / dur
        tb = score_track_b(dtw, int(ref_emb.shape[0]), int(lrn_emb.shape[0]),
                           pause_per_s=pps, pause_ratio=pr)
        with open(os.path.join(pair_dir, f"{pname}_problems.json"), "w") as f:
            json.dump({
                "accuracy": tb.accuracy, "fluency": tb.fluency,
                "speech_rate_ratio": tb.speech_rate_ratio,
                "raw_path_cost": tb.raw_path_cost,
                "problems": [
                    {"ref_start_s": p.ref_start_s, "ref_end_s": p.ref_end_s,
                     "severity": p.severity, "kind": p.kind}
                    for p in tb.problems
                ],
            }, f, indent=2)

        # FR-9 feedback: the rule engine's tips are what the learner reads, so
        # the Kotlin port must emit the same tip list for the same metrics.
        pcmp = compare_prosody(corpus[ref_k], corpus[lrn_k])
        payload = generate_feedback(tb, pcmp)
        with open(os.path.join(pair_dir, f"{pname}_feedback.json"), "w") as f:
            json.dump({
                "overall_score": payload["overall_score"],
                "overall_band": payload["overall_band"],
                "tips": payload["tips"],
                # the prosody NOTES are the Kotlin port's input (Track A stays
                # Python/Praat on macOS; on Android the notes come from the
                # Kotlin prosody module) — dump them so the feedback port can be
                # tested independently of the pitch extractor.
                "prosody_notes": pcmp.notes,
            }, f, indent=2, ensure_ascii=False)
        print(f"  problems/feedback {pname}: {len(tb.problems)} regions, "
              f"{len(payload['tips'])} tips")


def dump_word_diff(corpus, out_dir):
    """FR-7 golden: per-word improvement directions (读法改进方向).

    ``diagnose_words`` compares each FLAGGED reference word to its matched
    learner word acoustically — stress location (RMS envelope peak), duration
    ratio, pitch slope (Praat) — plus inter-word linking. The Kotlin port must
    reproduce the same tags and tips.

    Pitch is the one piece that cannot be ported bit-exactly (Praat's autocorr
    pitch tracker vs TarsosDSP YIN), so we dump BOTH:
      * the full macOS tips/tags (reference behaviour, includes pitch), and
      * a `no_pitch` variant with the pitch estimator disabled — the exactly
        reproducible subset the JVM test asserts on.
    The RMS envelope / stress position / duration logic IS bit-portable and is
    the bulk of the diagnosis; dumping the envelopes lets the port be checked
    element-wise rather than only through the verbaliser.
    """
    from backend.core import word_diff as wd
    from backend.core import forced_align as fa

    if not fa.is_available():
        print("  word_diff: SKIP (forced alignment unavailable)")
        return False

    wdir = os.path.join(out_dir, "worddiff")
    os.makedirs(wdir, exist_ok=True)
    names = SENTENCE.rstrip(".").split()

    # (case, ref_key, learner_key) — slow_samantha drags every word (duration
    # tags); crossvoice_daniel is a different speaker with its own stress/timing.
    cases = [("slow", "ref_samantha", "slow_samantha"),
             ("crossvoice", "ref_samantha", "crossvoice_daniel")]

    dumped = []
    for case, ref_k, lrn_k in cases:
        ref_wav, lrn_wav = corpus[ref_k], corpus[lrn_k]
        ref_spans = fa.align_words(names, ref_wav)
        lrn_spans = fa.align_words(names, lrn_wav)
        if not ref_spans or not lrn_spans:
            print(f"  word_diff {case}: SKIP (alignment returned nothing)")
            continue

        # Flag every word so the diagnosis runs on all of them (the real
        # pipeline gates on status; here we want maximum port coverage).
        ref_flat = [{"si": 0, "wi": i, "word": w, "start": sp[0], "end": sp[1],
                     "status": "weak"}
                    for i, (w, sp) in enumerate(zip(names, ref_spans)) if sp]
        learner_flat = [{"word": w, "start": sp[0], "end": sp[1]}
                        for w, sp in zip(names, lrn_spans) if sp]

        # the per-word acoustic primitives (bit-portable): RMS envelope +
        # stress position for both sides, so the Kotlin port is checked
        # element-wise, not just through the Chinese verbaliser.
        prims = []
        for r in ref_flat:
            li = next((i for i, l in enumerate(learner_flat)
                       if wd._norm(l["word"]) == wd._norm(r["word"])), None)
            if li is None:
                continue
            rs = wd._slice(ref_wav, r["start"], r["end"])
            ls = wd._slice(lrn_wav, learner_flat[li]["start"], learner_flat[li]["end"])
            renv, lenv = wd._rms_envelope(rs), wd._rms_envelope(ls)
            prims.append({
                "word": r["word"], "wi": r["wi"],
                "ref_start": r["start"], "ref_end": r["end"],
                "learner_start": learner_flat[li]["start"],
                "learner_end": learner_flat[li]["end"],
                "ref_stress_pos": wd._stress_pos(rs),
                "learner_stress_pos": wd._stress_pos(ls),
                "ref_env_len": 0 if renv is None else int(renv.size),
                "learner_env_len": 0 if lenv is None else int(lenv.size),
                "syllables": wd._syllables(r["word"]),
            })

        def _dump(tag, diffs):
            with open(os.path.join(wdir, f"{case}_{tag}.json"), "w") as f:
                json.dump({
                    "diffs": [
                        {"si": k[0], "wi": k[1], "word": v.word, "tip": v.tip,
                         "tags": v.tags,
                         "learner_start": v.learner_start, "learner_end": v.learner_end}
                        for k, v in sorted(diffs.items())
                    ],
                }, f, indent=2, ensure_ascii=False)

        _dump("tips", wd.diagnose_words(ref_wav, lrn_wav, ref_flat, learner_flat))

        # pitch-free variant: the exactly-reproducible subset (Praat's tracker
        # has no bit-exact JVM equivalent — see docs/android-migration.md §4).
        saved = wd._HAS_PRAAT
        wd._HAS_PRAAT = False
        try:
            _dump("tips_nopitch",
                  wd.diagnose_words(ref_wav, lrn_wav, ref_flat, learner_flat))
        finally:
            wd._HAS_PRAAT = saved

        with open(os.path.join(wdir, f"{case}_inputs.json"), "w") as f:
            json.dump({"ref": ref_flat, "learner": learner_flat,
                       "primitives": prims}, f, indent=2)
        dumped.append(case)
        print(f"  word_diff {case}: {len(ref_flat)} ref words, {len(prims)} primitives")

    return bool(dumped)


def dump_audio_io(corpus, out_dir):
    """audio_io.py: peak normalise, `librosa.effects.trim`, PCM_16 clip writing.

    Trim is load-bearing rather than cosmetic: it decides what enters the DTW
    *and* produces `learner_offset`, which FR-8 replay adds back. A boundary
    bug here shifts every score and every replay span, so the decision is
    captured explicitly instead of being inferred by diffing the trimmed and
    untrimmed corpus entries (those are two independent `say` runs — near
    identical here, but that is luck, not a contract).

    macOS `say` output carries almost no leading silence (trim removes ~10
    samples), so three synthetic cases are added on top of the real corpus:
    a zero pad (the real case — record-button latency), and two tone pads
    placed deliberately either side of the -30 dB threshold. The tone cases are
    what catch a wrong `amin`/`ref` in the dB chain: with a zero pad every
    plausible implementation agrees, because silence is -100 dB either way.
    """
    import soundfile as sf
    from librosa.effects import trim as lb_trim
    from librosa.feature import rms as lb_rms
    from librosa import amplitude_to_db

    TOP_DB = 30.0            # audio_io.trim_silence default
    FRAME, HOP = 2048, 512   # librosa.feature.rms defaults, via _signal_to_frame_nonsilent

    a_dir = os.path.join(out_dir, "audio")
    os.makedirs(a_dir, exist_ok=True)

    def frame_db(wav):
        r = lb_rms(y=wav, frame_length=FRAME, hop_length=HOP)[..., 0, :]
        return r, amplitude_to_db(r, ref=np.max, top_db=None)

    def record(name, wav):
        trimmed, idx = lb_trim(wav, top_db=TOP_DB)
        np.save(os.path.join(a_dir, f"{name}_in.npy"), wav.astype("float32"))
        return {
            "name": name,
            "n_in": int(wav.size),
            "start": int(idx[0]),
            "end": int(idx[1]),
            "n_out": int(trimmed.size),
            # trim_silence_with_offset's return value — FR-8 replay adds this back
            "offset_s": round(float(idx[0]) / TARGET_SR, 6),
        }

    cases = []
    for name in [c[0] for c in CORPUS]:
        cases.append(record(name, corpus[name]))

    # --- synthetic pads on the reference (already peak-normalised, pre-trim) ---
    speech = corpus["ref_samantha_raw"]
    max_rms = float(np.max(frame_db(speech)[0]))
    lead, tail = int(0.30 * TARGET_SR), int(0.17 * TARGET_SR)

    def tone(n, amp, f=200.0):
        t = np.arange(n, dtype="float64") / TARGET_SR
        return (amp * np.sin(2 * np.pi * f * t)).astype("float32")

    def at_db(db):
        """Constant tone whose frame RMS sits `db` below the speech's loudest frame."""
        return float(max_rms * (10.0 ** (db / 20.0)) * np.sqrt(2.0))

    pads = {
        # the real-world case: dead-silent lead-in from record-button latency
        "pad_zero": (np.zeros(lead, "float32"), np.zeros(tail, "float32")),
        # 4 dB below the threshold -> must be trimmed away
        "pad_below": (tone(lead, at_db(-TOP_DB - 4.0)), tone(tail, at_db(-TOP_DB - 4.0))),
        # 4 dB above the threshold -> counts as signal, must be KEPT (start == 0)
        "pad_above": (tone(lead, at_db(-TOP_DB + 4.0)), tone(tail, at_db(-TOP_DB + 4.0))),
    }
    for name, (pre, post) in pads.items():
        padded = np.concatenate([pre, speech, post]).astype("float32")
        c = record(name, padded)
        c["lead_samples"] = int(pre.size)
        cases.append(c)

    # frame-level intermediates for ONE case, so a failure says which stage broke
    # (RMS framing vs the dB conversion vs the threshold vs frame->sample).
    probe = np.concatenate([pads["pad_zero"][0], speech, pads["pad_zero"][1]]).astype("float32")
    r, db = frame_db(probe)
    np.save(os.path.join(a_dir, "pad_zero_rms.npy"), r.astype("float32"))
    np.save(os.path.join(a_dir, "pad_zero_db.npy"), db.astype("float32"))

    # --- peak normalisation (audio_io._normalize) ---
    from backend.core.audio_io import _normalize
    norm_cases = []
    for label, raw in [
        ("loud", (speech * 3.0).astype("float32")),
        ("quiet", (speech * 0.01).astype("float32")),
        # peak <= 1e-6 is left alone rather than amplified — otherwise a silent
        # take would be blown up to full scale and scored as speech.
        ("near_silent", np.full(1024, 5e-7, "float32")),
        ("all_zero", np.zeros(512, "float32")),
    ]:
        out = _normalize(raw.copy())
        np.save(os.path.join(a_dir, f"norm_{label}_in.npy"), raw)
        np.save(os.path.join(a_dir, f"norm_{label}_out.npy"), out)
        norm_cases.append({
            "label": label,
            "peak_in": float(np.max(np.abs(raw))) if raw.size else 0.0,
            "peak_out": float(np.max(np.abs(out))) if out.size else 0.0,
            "scaled": bool(not np.array_equal(raw, out)),
        })

    with open(os.path.join(a_dir, "trim.json"), "w") as f:
        json.dump({"top_db": TOP_DB, "frame_length": FRAME, "hop_length": HOP,
                   "sr": TARGET_SR, "cases": cases, "normalize": norm_cases},
                  f, indent=2)

    # --- PCM_16 clip writing (FR-8: main.py /clip + /recordings/{id}/clip) ---
    clip = corpus["ref_samantha"][8000:24000]
    np.save(os.path.join(a_dir, "clip_in.npy"), clip.astype("float32"))
    sf.write(os.path.join(a_dir, "clip_pcm16.wav"), clip, TARGET_SR,
             format="WAV", subtype="PCM_16")
    # what soundfile reads back — pins the *reader* too (int16 -> float scaling)
    back, sr_back = sf.read(os.path.join(a_dir, "clip_pcm16.wav"), dtype="float32")
    assert sr_back == TARGET_SR
    np.save(os.path.join(a_dir, "clip_roundtrip.npy"), back.astype("float32"))

    print(f"  audio_io: {len(cases)} trim cases, {len(norm_cases)} normalise cases, "
          f"clip {clip.size} samples -> "
          f"{os.path.getsize(os.path.join(a_dir, 'clip_pcm16.wav'))} bytes")
    return True


def dump_resample(corpus, out_dir):
    """R-9 / Gate E golden: polyphase resampling to 16 kHz.

    On Android the reference audio comes out of MediaCodec at the container's
    native rate and has to be resampled in-process; the learner's never is
    (AudioRecord captures at 16 kHz). R-9 measured that *which* resampler is
    used does not move a score — see
    ``docs/reviews/2026-07-26-android-gate-e-audio-decode.md`` and
    ``scripts/resampler_parity.py``. What is captured here is the narrower and
    much stricter claim that the Kotlin port reproduces the exact resampler
    that measurement was made with, `scipy.signal.resample_poly` with its
    default Kaiser(5.0) design.

    Deliberately float64 on both sides. The production path is float32, but a
    float32 golden would confound two different things — an algorithmic bug and
    accumulation order — and only the first is worth a test. The float32 path
    is checked separately, against this one, with an SNR bound.

    Speech cases are built by *upsampling* the 16 kHz corpus rather than by
    reading a video, so the fixture reproduces from `say` alone.
    """
    import librosa
    from scipy.signal import resample_poly

    r_dir = os.path.join(out_dir, "resample")
    os.makedirs(r_dir, exist_ok=True)

    def tone(sr: int, dur: float) -> np.ndarray:
        n = np.arange(int(sr * dur))
        # The 11 kHz partial is above the 8 kHz output Nyquist on purpose: it is
        # what a missing or wrong anti-alias filter folds back audibly.
        return (
            0.50 * np.sin(2 * np.pi * 440.0 * n / sr)
            + 0.30 * np.sin(2 * np.pi * 3000.0 * n / sr)
            + 0.10 * np.sin(2 * np.pi * 7500.0 * n / sr)
            + 0.05 * np.sin(2 * np.pi * 11000.0 * n / sr)
        )

    speech16 = corpus["ref_samantha"].astype("float64")[: 16000 // 2]  # 0.5 s
    cases = []
    for name, sr_in, x in (
        ("tone_44k1", 44100, tone(44100, 0.25)),
        ("tone_48k", 48000, tone(48000, 0.25)),
        ("speech_44k1", 44100,
         librosa.resample(speech16, orig_sr=16000, target_sr=44100, res_type="soxr_hq")),
        ("speech_48k", 48000,
         librosa.resample(speech16, orig_sr=16000, target_sr=48000, res_type="soxr_hq")),
    ):
        g = math.gcd(sr_in, TARGET_SR)
        up, down = TARGET_SR // g, sr_in // g
        y = resample_poly(x, up, down)
        np.save(os.path.join(r_dir, f"{name}_in.npy"), x)
        np.save(os.path.join(r_dir, f"{name}_out.npy"), y)
        cases.append({
            "name": name, "sr_in": sr_in, "sr_out": TARGET_SR,
            "up": up, "down": down, "n_in": int(x.size), "n_out": int(y.size),
            "half_len": 10 * max(up, down), "numtaps": 2 * (10 * max(up, down)) + 1,
        })
        print(f"  resample: {name} {sr_in}->{TARGET_SR} (up={up} down={down}) "
              f"{x.size} -> {y.size} samples")

    meta = {
        "producer": "scipy.signal.resample_poly, window=('kaiser', 5.0) (default)",
        "dtype": "float64",
        "design": {
            "cutoff_rel_nyquist": "1 / max(up, down)",
            "half_len": "10 * max(up, down)",
            "kaiser_beta": 5.0,
            "gain": "sum(h) normalised to 1, then scaled by `up`",
        },
        "gate": "R-9 / Gate E",
        "cases": cases,
    }
    with open(os.path.join(r_dir, "resample.json"), "w") as f:
        json.dump(meta, f, indent=2)
    return True


def dump_segmentation(out_dir):
    """FR-2 / FR-M3 golden: whisper words -> sentences (transcribe.py).

    Two entry points with deliberately different behaviour, both captured:

    * the *reference* path (`_merge_words_into_sentences`) merges by terminal
      punctuation and then sub-splits over-long sentences at clause boundaries;
    * the *learner* path (`_merge_into_sentences`, via `transcribe_waveform`)
      merges by punctuation only — no sub-split, because the learner's chunks
      have to line up with the reference sentence they chose to shadow.

    The main fixture is the real cached transcript (``videos/*.sentences.json``):
    1944 whisper words -> 164 sentences, and because `emit` copies its words
    through unchanged, concatenating the cached sentences' words recovers the
    exact input the merge saw. That is worth far more than synthetic text here —
    it carries the messy tokens whisper actually produces ("long -considered",
    leading-dash words, quoted clause ends) and it exercises 62 sub-splits,
    47 punctuation cuts, 12 conjunction cuts, 4 midpoint ties and 3 give-ups.

    Synthetic cases cover the branches the corpus happens to miss (trailing
    words with no terminal punctuation, learner-path no-split, rounding). Every
    expectation is produced by calling the real functions, so the fixture states
    macOS's behaviour rather than my belief about it.
    """
    from backend.core import transcribe as T

    cache = cache_path = None
    for cand in glob.glob(os.path.join("videos", "*.sentences.json")):
        with open(cand, "r", encoding="utf-8") as f:
            d = json.load(f)
        if d.get("version") == T.CACHE_VERSION and d.get("sentences"):
            cache, cache_path = d, cand
            break

    s_dir = os.path.join(out_dir, "seg")
    os.makedirs(s_dir, exist_ok=True)

    def strip(w):
        return {"word": w["word"], "start": w["start"], "end": w["end"]}

    ref_meta = None
    if cache is not None:
        words = [strip(w) for s in cache["sentences"] for w in s["words"]]
        sents = T._merge_words_into_sentences([dict(w) for w in words])
        # the cache was written by this same function, so this must hold; assert
        # it rather than trust it, because a silent mismatch would mean the
        # fixture encodes a stale schema instead of today's behaviour.
        assert sents == cache["sentences"], "re-merge does not reproduce the cache"
        with open(os.path.join(s_dir, "reference_words.json"), "w") as f:
            json.dump(words, f, ensure_ascii=False)
        with open(os.path.join(s_dir, "reference_sentences.json"), "w") as f:
            json.dump(sents, f, ensure_ascii=False)
        ref_meta = {
            "source": os.path.basename(cache_path),
            "cache_version": T.CACHE_VERSION,
            "n_words": len(words),
            "n_sentences": len(sents),
        }
        print(f"  segmentation: {len(words)} words -> {len(sents)} sentences "
              f"({ref_meta['source']})")

    # --- synthetic cases -----------------------------------------------------
    def W(spec):
        """"word@start:end" -> word dict (times in seconds)."""
        out, t = [], 0.0
        for tok in spec:
            if isinstance(tok, tuple):
                out.append({"word": tok[0], "start": tok[1], "end": tok[2]})
            else:
                out.append({"word": tok, "start": round(t, 3), "end": round(t + 0.4, 3)})
                t += 0.5
        return out

    class _FakeWord:
        def __init__(self, d):
            self.word, self.start, self.end = d["word"], d["start"], d["end"]

    class _FakeSeg:
        """One whisper segment. `words=None` reaches the pseudo-word fallback."""
        def __init__(self, words, text=None, start=0.0, end=0.0):
            self.words = [_FakeWord(w) for w in words] if words is not None else None
            self.text = text or " ".join(w["word"] for w in (words or []))
            self.start, self.end = start, end

    def learner(words):
        return T._merge_into_sentences([_FakeSeg(words)])

    long_words = ["word%d" % i for i in range(24)]
    cases = [
        ("trailing_no_punct", True,
         "the final flush: a stream that never ends in .!? still emits a sentence",
         W(["Hello", "there", "friend"])),
        ("two_sentences", True, "flush fires on the terminal-punctuation word",
         W(["One", "two.", "Three", "four!"])),
        ("quoted_terminal", True, "terminal punctuation followed by a closing quote",
         W(["He", 'said', '"go."', "Then", "left)."])),
        ("whitespace_collapse", True, "emit() collapses runs of whitespace in the text",
         W([" spaced ", "out\ttoken", "end."])),
        # Python's \s and str.strip() are Unicode-aware and include NBSP; Java's
        # \s is ASCII-only and Character.isWhitespace() excludes NBSP by design.
        # Whisper is unlikely to emit these, but the divergence is silent.
        ("whitespace_unicode", True, "NBSP / line-separator count as whitespace in Python",
         W(["\xa0nbsp\xa0", "line\u2028sep", "\u3000wide", "tail\x85."])),
        ("clause_split_punct", True, "a >20-word sentence cut at a comma near the middle",
         W(["a", "b", "c", "d", "e", "f,", "g", "h", "i", "j", "k", "l",
            "m", "n", "o", "p", "q", "r", "s", "t", "u", "v."])),
        ("conj_split_capitalised", True,
         "conjunction match strips leading non-letters and lowercases: '-And'",
         W(["a", "b", "c", "d", "e", "f", "g", "h", "-And", "j", "k", "l",
            "m", "n", "o", "p", "q", "r", "s", "t", "u", "v."])),
        ("no_candidate_stays_long", True,
         "over-long with no clause punctuation and no conjunction -> left whole",
         W(long_words[:-1] + ["last."])),
        ("too_short_to_split", True,
         "long in seconds but under 2*_MIN_CHUNK_WORDS -> never split",
         W([("aaa", 0.0, 3.0), ("bbb", 3.0, 6.0), ("ccc", 6.0, 9.0), ("ddd", 9.0, 12.5)])),
        ("duration_trigger", True,
         "under 20 words but over 8s -> the duration branch of _needs_split",
         W([(w, i * 0.9, i * 0.9 + 0.8) for i, w in enumerate(
             ["a", "b", "c", "d,", "e", "f", "g", "h", "i", "j", "k."])])),
        # 48 words at 0.5s each: the first cut leaves two 24-word halves, each
        # still over both limits, so _split_long has to recurse into them. A
        # single-level implementation returns 2 sentences here instead of 4.
        ("recursive_split", True, "each half is re-tested, so one call cuts more than once",
         W(["w%d%s" % (i, "," if i % 6 == 5 else "") for i in range(47)] + ["end."])),
        ("empty", True, "no words -> no sentences", []),
        ("single_word", True, "one word, no punctuation", W(["Hi"])),
    ]

    def round_words(words):
        """`_aligned_words`' closing loop: the reference path always hands the
        merge 3-dp times, so a case built with raw floats would pin behaviour the
        pipeline can't reach (and would demand that Kotlin keep 1.7000000000000002
        verbatim). The learner cases below stay raw on purpose — that path does
        its own rounding, which is the thing worth testing."""
        return [{"word": w["word"], "start": round(w["start"], 3),
                 "end": round(w["end"], 3)} for w in words]

    dumped = []
    for name, subsplit, note, words in cases:
        words = round_words(words)
        expect = T._merge_words_into_sentences([dict(w) for w in words])
        dumped.append({"name": name, "subsplit": subsplit, "note": note,
                       "words": words, "expect": expect})

    # learner path: the SAME over-long input must come back as one sentence
    for name, note, words in [
        ("learner_long_not_split", "no sub-split on the learner path (FR-M3 is reference-only)",
         W(["a", "b", "c", "d,", "e", "f", "g", "h", "i", "j", "k", "l",
            "m", "n", "o", "p", "q", "r", "s", "t", "u", "v."])),
        ("learner_raw_times_rounded",
         "raw model times are rounded to 3dp on the way in — Python round() is "
         "round-half-EVEN on the exact binary value, so 0.0625 -> 0.062",
         W([("Raw", 0.0625, 0.1875), ("times.", 0.5625, 1.0625)])),
    ]:
        dumped.append({"name": name, "subsplit": False, "note": note,
                       "words": words, "expect": learner(words)})

    # the pseudo-word fallback: a segment with no word timestamps keeps its text
    seg_fallback = [
        {"words": None, "text": "  A whole segment.  ", "start": 1.2345, "end": 3.5},
        {"words": [{"word": "then", "start": 3.6, "end": 3.9},
                   {"word": "more.", "start": 3.9, "end": 4.4}], "text": None},
    ]
    fallback_expect = T._merge_into_sentences([
        _FakeSeg(s["words"], s["text"], s.get("start", 0.0), s.get("end", 0.0))
        for s in seg_fallback
    ])

    # Python round(x, 3) on values chosen to be exact binary ties — the two
    # obvious Kotlin idioms (`round`, "%.3f") are half-UP and get these wrong.
    round3 = [{"in": x, "out": round(x, 3)} for x in
              [0.0625, 0.1875, 1.0625, 3.0625, 0.5625, 2.1875, 0.0005, 1.0005,
               2.6755, 8.8345, 0.1235, 636.1335, 0.0, -0.0625]]

    # The two regexes, probed directly. `$` differs between the languages: Python
    # allows only a trailing "\n" before it, Java also allows \r, \x85, \u2028
    # and \u2029 -- so "done.\u2028" is a sentence end in Java but not in Python.
    probes = ["ok.", "ok!", "ok?", "ok", "ok.'", 'ok."', "ok.)", "ok.]", "ok.}",
              "ok..", "o.k.", "ok. ", "ok.\n", "ok.\u2028", "ok.\r", "ok.\x85",
              "U.S.", "3.5", "", ".", "?", "'", "ok,", "ok;", "ok:", "ok,'",
              'ok,"', "ok, ", "ok,\n", "ok,\u2028", "-and", "And", "AND",
              "—but", "b.ut", "and", "andy", "-", "12and"]
    regexes = [{"token": t,
                "sentence_end": bool(T._SENTENCE_END.search(t)),
                "clause_end": bool(T._CLAUSE_END.search(t)),
                "conj_key": re.sub(r"^[^a-zA-Z]+", "", t).lower(),
                "is_conj": re.sub(r"^[^a-zA-Z]+", "", t).lower() in T._CONJ,
                "py_strip": t.strip()}
               for t in probes]

    # _best_split_point probed directly, so a tie-break or off-by-one in the
    # candidate range is reported as itself instead of as a wrong sentence count.
    def sp(*toks):
        return [{"word": t, "start": i * 0.5, "end": i * 0.5 + 0.4}
                for i, t in enumerate(toks)]

    split_points = []
    for name, toks in [
        # two comma candidates equidistant from the midpoint (i=4 and i=6, mid=5)
        ("tie_prefers_lower_index", ["a", "b", "c", "d,", "e", "f,", "g", "h", "i", "j"]),
        # a conjunction sits exactly at the midpoint, a comma sits far from it:
        # rank beats distance, so the comma wins
        ("punctuation_outranks_a_nearer_conjunction",
         ["a", "b", "c", "d,", "e", "f", "g", "and", "i", "j", "k", "l", "m", "n"]),
        # candidate at the very first legal index (i == _MIN_CHUNK_WORDS)
        ("first_legal_index", ["a", "b", "c", "d,", "e", "f", "g", "h"]),
        # candidate at the very last legal index (i == n - _MIN_CHUNK_WORDS, so
        # the comma is on word n-MIN-1 and the right chunk is exactly MIN long)
        ("last_legal_index", ["a", "b", "c", "d", "e", "f,", "g", "h", "i", "j"]),
        # ...and one word further on is out of range: the right chunk would be
        # 3 words, so the comma is ignored and the sentence stays whole
        ("beyond_last_legal_index", ["a", "b", "c", "d", "e", "f", "g,", "h", "i", "j"]),
        # a comma inside the forbidden margin must be ignored
        ("margin_is_excluded", ["a", "b,", "c", "d", "e", "f", "g", "h,", "i", "j", "k", "l"]),
        ("no_candidate", ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]),
        ("too_few_words", ["a", "b", "c,", "d", "e", "f", "g"]),
    ]:
        words = sp(*toks)
        split_points.append({"name": name, "words": words,
                             "expect": T._best_split_point(words)})

    # Every code point Python calls whitespace. `str.strip()` and `\s` use this
    # set; Java's Character.isWhitespace() deliberately excludes the no-break
    # spaces (\xa0, \u2007, \u202f) and knows nothing about \x85, so the Kotlin
    # predicate has to be assembled from isWhitespace + isSpaceChar + \x85.
    pyspace = [i for i in range(0x10000) if chr(i).isspace()]

    with open(os.path.join(s_dir, "segmentation.json"), "w") as f:
        json.dump({
            "split_dur_s": T._SPLIT_DUR_S,
            "split_words": T._SPLIT_WORDS,
            "min_chunk_words": T._MIN_CHUNK_WORDS,
            "conjunctions": sorted(T._CONJ),
            "reference": ref_meta,
            "cases": dumped,
            "segment_fallback": {"segments": seg_fallback, "expect": fallback_expect},
            "round3": round3,
            "regexes": regexes,
            "split_points": split_points,
            "pyspace": pyspace,
        }, f, indent=2, ensure_ascii=False)

    n_split = sum(1 for c in dumped if len(c["expect"]) > 1)
    print(f"  segmentation: {len(dumped)} synthetic cases ({n_split} multi-sentence), "
          f"{len(round3)} rounding probes")
    return True


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

        print("-- word diff (FR-7) --")
        wd_ok = dump_word_diff(corpus, out_dir)

        print("-- audio_io: trim / normalise / PCM_16 clip (FR-3 / FR-8) --")
        audio_ok = dump_audio_io(corpus, out_dir)

        print("-- polyphase resampling (R-9 / Gate E) --")
        resample_ok = dump_resample(corpus, out_dir)

        print("-- sentence segmentation (FR-2 / FR-M3) --")
        seg_ok = dump_segmentation(out_dir)

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
            "emb": True, "pair": True, "worddiff": wd_ok,
            "audio": audio_ok, "resample": resample_ok, "seg": seg_ok, "mms": mms_ok, "espeak": espeak_ok,
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
            "worddiff/<case>_tips.json is the full macOS diagnosis (includes "
            "Praat pitch); _tips_nopitch.json is the pitch-free subset the JVM "
            "test asserts exactly, since Praat's tracker has no bit-exact JVM "
            "equivalent (TarsosDSP YIN differs). _inputs.json carries the word "
            "spans + the RMS/stress primitives for element-wise port checking.",
            "audio/trim.json pins librosa.effects.trim's [start, end] sample "
            "indices per case; the Kotlin port must match them EXACTLY (they "
            "set both the DTW input and FR-8's learner_offset). pad_above / "
            "pad_below straddle the -30dB threshold on purpose — a zero pad is "
            "-100dB and agrees under any dB chain, so it proves nothing about "
            "amin/ref. audio/clip_pcm16.wav is soundfile's PCM_16 output, "
            "byte-comparable against the Kotlin WAV writer.",
            "seg/reference_{words,sentences}.json is the real cached transcript "
            "(videos/*.sentences.json) taken apart and re-merged: 1944 whisper "
            "words -> 164 sentences, exercising 62 FR-M3 sub-splits including "
            "midpoint ties. seg/segmentation.json adds the branches the corpus "
            "misses and pins that the LEARNER path does not sub-split. round3 "
            "holds exact binary ties (0.0625 -> 0.062): Python round() is "
            "half-EVEN, so Kotlin's round / \"%.3f\" are both wrong there.",
            "pair/<name>_problems.json is score_track_b's full result (FR-4 "
            "regions are exact-comparable); pair/<name>_feedback.json is the "
            "FR-9 rule engine's tip list keyed off those metrics + the Track-A "
            "prosody notes (dumped so the port is testable without Praat).",
        ],
    }
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"== done. manifest at {os.path.join(out_dir, 'manifest.json')} ==")


if __name__ == "__main__":
    main()
