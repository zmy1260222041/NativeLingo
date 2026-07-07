"""End-to-end Track B pipeline: reference + learner audio -> scores + regions.

This wires together the reverse-evaluation idea:

    load -> trim silence -> SSL encode -> speaker-normalise -> DTW align -> score

The pipeline is deliberately stateless except for the (cached) encoder, so the
backend can call ``analyze`` per request.
"""
from __future__ import annotations

from dataclasses import asdict

import numpy as np

from .audio_io import load_audio, trim_silence, trim_silence_with_offset, TARGET_SR
from .transcribe import transcribe_waveform
from .word_diff import diagnose_words
from .ssl_encoder import SSLEncoder
from .speaker_norm import normalize_pair
from .align import dtw_align
from .score_b import score_track_b, TrackBResult
from .prosody import compare_prosody
from .feedback import generate_feedback
from .detail import compute_sentence_details
from dataclasses import asdict as _asdict

_encoder: SSLEncoder | None = None


def get_encoder() -> SSLEncoder:
    """Lazily construct and reuse a single encoder (weights load once)."""
    global _encoder
    if _encoder is None:
        _encoder = SSLEncoder()
    return _encoder


def analyze_arrays(ref_wav: np.ndarray, learner_wav: np.ndarray) -> TrackBResult:
    """Run Track B on two preloaded 16 kHz mono waveforms.

    Assumes silence has already been trimmed by the caller.
    """
    encoder = get_encoder()

    ref_emb = encoder.encode(ref_wav)
    learner_emb = encoder.encode(learner_wav)

    ref_n, learner_n = normalize_pair(ref_emb, learner_emb)
    dtw = dtw_align(ref_n, learner_n)
    return score_track_b(dtw, ref_emb.shape[0], learner_emb.shape[0])


def analyze_files(ref_path: str, learner_path: str) -> TrackBResult:
    """Run Track B on two audio file paths."""
    ref_wav = trim_silence(load_audio(ref_path))
    learner_wav = trim_silence(load_audio(learner_path))
    return analyze_arrays(ref_wav, learner_wav)


def result_to_dict(result: TrackBResult) -> dict:
    """JSON-serialisable view of a result (for the API layer)."""
    d = asdict(result)
    return d


def analyze_full(ref_wav: np.ndarray, learner_wav: np.ndarray) -> dict:
    """Full MVP analysis: Track B + prosody (Track A) + feedback (Track C).

    Returns the complete JSON-serialisable payload the frontend consumes.
    """
    ref_wav = trim_silence(ref_wav)
    learner_wav = trim_silence(learner_wav)

    track_b = analyze_arrays(ref_wav, learner_wav)
    prosody = compare_prosody(ref_wav, learner_wav)
    return generate_feedback(track_b, prosody)


def analyze_full_files(ref_path: str, learner_path: str) -> dict:
    return analyze_full(load_audio(ref_path), load_audio(learner_path))


def analyze_detailed(
    ref_wav: np.ndarray,
    learner_wav: np.ndarray,
    ref_sentences: list[dict],
) -> dict:
    """Full analysis + per-sentence/per-word breakdown.

    ``ref_sentences``: sentences with clip-relative timings and words, i.e.
    [{index, text, start, end, words:[{word, start, end}]}]. The reference clip
    is NOT silence-trimmed here so those timestamps map straight onto frames;
    only the learner recording is trimmed.
    """
    encoder = get_encoder()
    # keep the original (untrimmed) recording: its timeline matches the blob the
    # frontend replays, and we segment it independently below
    orig_learner = learner_wav
    # trim only for alignment/scoring; keep the offset so the DTW-fallback spans
    # still map back onto the original recording
    learner_trimmed, learner_offset = trim_silence_with_offset(learner_wav)

    ref_emb = encoder.encode(ref_wav)
    learner_emb = encoder.encode(learner_trimmed)
    ref_n, learner_n = normalize_pair(ref_emb, learner_emb)
    dtw = dtw_align(ref_n, learner_n)

    track_b = score_track_b(dtw, ref_emb.shape[0], learner_emb.shape[0])
    prosody = compare_prosody(ref_wav, learner_trimmed)
    payload = generate_feedback(track_b, prosody)

    details = compute_sentence_details(dtw, ref_sentences, learner_offset=learner_offset)

    # Independent learner segmentation: the learner's replay boundaries should
    # come from *their own* audio, not from warping the reference's timing onto
    # it (different speech rate clips words at sentence borders). When the
    # learner's own transcription segments 1:1 with the reference range, use its
    # natural spans (with a small pad); otherwise keep the DTW-derived fallback.
    try:
        learner_sents = transcribe_waveform(orig_learner)
    except Exception:  # noqa: BLE001 — never fail analysis over replay spans
        learner_sents = []
    if learner_sents and len(learner_sents) == len(details):
        dur = len(orig_learner) / float(TARGET_SR)
        for d, ls in zip(details, learner_sents):
            d.learner_start = round(max(0.0, ls["start"] - 0.1), 2)
            d.learner_end = round(min(dur, ls["end"] + 0.15), 2)

    # --- per-word pronunciation improvement directions (读法改进方向) ---
    # Compare each flagged reference word to the matched learner word and name
    # the acoustic difference (stress, linking, length, pitch) in words.
    ref_flat = [
        {"si": d.index, "wi": wi, "word": w.word,
         "start": w.start, "end": w.end, "status": w.status}
        for d in details
        for wi, w in enumerate(d.words)
    ]
    learner_flat = [
        {"word": w["word"], "start": w["start"], "end": w["end"]}
        for s in learner_sents
        for w in s.get("words", [])
    ]
    try:
        diffs = diagnose_words(ref_wav, orig_learner, ref_flat, learner_flat)
    except Exception:  # noqa: BLE001 - never let diagnosis break the response
        diffs = {}
    for d in details:
        for wi, w in enumerate(d.words):
            wd = diffs.get((d.index, wi))
            if wd is not None:
                w.tip = wd.tip
                w.learner_start = wd.learner_start
                w.learner_end = wd.learner_end

    payload["sentences"] = [_asdict(d) for d in details]
    return payload
