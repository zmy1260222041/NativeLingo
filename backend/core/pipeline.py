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
from . import forced_align
from .word_diff import diagnose_words
from .ssl_encoder import SSLEncoder
from .speaker_norm import normalize_pair
from .align import dtw_align
from .score_b import score_track_b, TrackBResult
from .prosody import compare_prosody, extract_prosody, ProsodyFeatures
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


def _pause_feats(p: ProsodyFeatures) -> tuple[float, float]:
    """(pauses/sec, pause-time ratio) for the calibrated fluency regression."""
    dur = max(p.duration_s, 1e-3)
    return p.num_pauses / dur, p.total_pause_s / dur


def analyze_arrays(ref_wav: np.ndarray, learner_wav: np.ndarray) -> TrackBResult:
    """Run Track B on two preloaded 16 kHz mono waveforms.

    Assumes silence has already been trimmed by the caller.
    """
    encoder = get_encoder()

    ref_emb = encoder.encode(ref_wav)
    learner_emb = encoder.encode(learner_wav)

    ref_n, learner_n = normalize_pair(ref_emb, learner_emb)
    dtw = dtw_align(ref_n, learner_n)
    pps, pr = _pause_feats(extract_prosody(learner_wav))
    return score_track_b(
        dtw, ref_emb.shape[0], learner_emb.shape[0], pause_per_s=pps, pause_ratio=pr
    )


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

    prosody = compare_prosody(ref_wav, learner_trimmed)
    pps, pr = _pause_feats(prosody.learner)
    track_b = score_track_b(
        dtw, ref_emb.shape[0], learner_emb.shape[0], pause_per_s=pps, pause_ratio=pr
    )
    payload = generate_feedback(track_b, prosody)

    details = compute_sentence_details(dtw, ref_sentences, learner_offset=learner_offset)
    dur = len(orig_learner) / float(TARGET_SR)

    # Per-word reference text, flat, in selected-range order.
    ref_flat = [
        {"si": d.index, "wi": wi, "word": w.word,
         "start": w.start, "end": w.end, "status": w.status}
        for d in details
        for wi, w in enumerate(d.words)
    ]

    # Learner replay spans: align the REFERENCE text to the learner's audio.
    # Because we align the intended transcript (not an ASR decode of what was
    # actually said), a mispronounced word still maps 1:1 to the word it should
    # be -- the aligner finds the best monotonic fit of that text to the audio
    # regardless of how clearly it was pronounced. This also yields a replay
    # span for *every* word (not just flagged ones) and drops the difflib match.
    learner_flat: list[dict] = []
    try:
        aligned = forced_align.align_words([r["word"] for r in ref_flat], orig_learner)
    except Exception:  # noqa: BLE001 - never fail analysis over replay spans
        aligned = None
    aligned_ok = aligned is not None

    if aligned_ok:
        idx = 0
        for d in details:
            sent_starts: list[float] = []
            sent_ends: list[float] = []
            for w in d.words:
                sp = aligned[idx] if idx < len(aligned) else None
                idx += 1
                lw = {"word": w.word, "start": 0.0, "end": 0.0}
                if sp is not None:
                    s = max(0.0, sp[0] - 0.03)   # small head/tail pad so the
                    e = min(dur, sp[1] + 0.06)   # clip isn't shaved at the edges
                    w.learner_start = round(s, 3)
                    w.learner_end = round(e, 3)
                    lw["start"], lw["end"] = w.learner_start, w.learner_end
                    sent_starts.append(s)
                    sent_ends.append(e)
                learner_flat.append(lw)
            if sent_starts:
                d.learner_start = round(max(0.0, min(sent_starts) - 0.05), 2)
                d.learner_end = round(min(dur, max(sent_ends) + 0.10), 2)
    else:
        # Fallback: independent learner transcription + difflib match.
        try:
            learner_sents = transcribe_waveform(orig_learner)
        except Exception:  # noqa: BLE001
            learner_sents = []
        if learner_sents and len(learner_sents) == len(details):
            for d, ls in zip(details, learner_sents):
                d.learner_start = round(max(0.0, ls["start"] - 0.1), 2)
                d.learner_end = round(min(dur, ls["end"] + 0.15), 2)
        learner_flat = [
            {"word": w["word"], "start": w["start"], "end": w["end"]}
            for s in learner_sents
            for w in s.get("words", [])
        ]

    # --- per-word pronunciation improvement directions (读法改进方向) ---
    # diagnose_words compares each flagged reference word to the matched learner
    # word and names the acoustic difference (stress, linking, length, pitch).
    try:
        diffs = diagnose_words(ref_wav, orig_learner, ref_flat, learner_flat)
    except Exception:  # noqa: BLE001 - never let diagnosis break the response
        diffs = {}
    for d in details:
        for wi, w in enumerate(d.words):
            wd = diffs.get((d.index, wi))
            if wd is not None:
                w.tip = wd.tip
                # keep the alignment-derived span (accurate); only let diagnosis
                # supply the word span in the no-alignment fallback path.
                if not aligned_ok and wd.learner_end > wd.learner_start:
                    w.learner_start = wd.learner_start
                    w.learner_end = wd.learner_end

    # --- phoneme-level substitution diagnosis (FR-11, MDD) ---
    # For flagged words with a learner span, decode the REFERENCE span to a
    # canonical IPA sequence, then score single-phoneme substitution/deletion
    # hypotheses against the learner's CTC emissions (Viterbi). A gain past
    # margin names the actual substitution ("/θ/ 读成了 /s/"); prepended to the
    # prosody tip. See phoneme.py + docs/reviews/2026-07-23-mdd-phoneme-fit.md.
    try:
        from . import phoneme

        if phoneme.is_available():
            for d in details:
                for w in d.words:
                    if w.status not in ("weak", "bad"):
                        continue
                    if w.learner_end <= w.learner_start:
                        continue
                    ptip = phoneme.diagnose_word_span(
                        ref_wav, w.start, w.end,
                        orig_learner, w.learner_start, w.learner_end,
                        w.word,
                    )
                    if ptip:
                        w.tip = (ptip + " " + w.tip).strip()
    except Exception:  # noqa: BLE001 - phoneme track must never break analysis
        pass

    payload["sentences"] = [_asdict(d) for d in details]
    return payload
