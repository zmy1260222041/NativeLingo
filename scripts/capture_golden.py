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
            "audio": audio_ok, "mms": mms_ok, "espeak": espeak_ok,
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
