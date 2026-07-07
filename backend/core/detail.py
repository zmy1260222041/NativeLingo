"""Per-sentence and per-word breakdown (细节评估).

Reuses the Track B DTW alignment to localise errors. The DTW path maps every
reference frame to a learner frame with a cosine distance (the accuracy signal).
Given the reference's word/sentence timestamps (clip-relative seconds), we:

* find the path entries whose reference frame falls in each word/sentence span
* average their cosine distance -> that unit's accuracy
* use the learner-frame span vs reference-frame span -> that unit's timing/fluency
* flag likely mispronounced / skipped words

No extra model needed — this is a projection of the existing alignment onto the
transcript's time grid.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .align import DTWResult
from .ssl_encoder import FRAME_RATE_HZ
from .score_b import _lin_map, ACC_DIST_GOOD, ACC_DIST_BAD

# A word whose aligned cosine distance exceeds this is flagged as a problem.
WORD_PROBLEM_DIST = 0.42
# If a reference word maps to very few learner frames, it was likely skipped.
MIN_COVER_RATIO = 0.35


@dataclass
class WordDetail:
    word: str
    start: float          # clip-relative reference seconds
    end: float
    accuracy: float       # 0-100
    status: str           # "good" | "weak" | "bad" | "missed"
    tip: str = ""         # 读法改进方向 (filled in by word_diff, "" if none)
    learner_start: float = 0.0  # matched learner-recording span (for A/B replay)
    learner_end: float = 0.0


@dataclass
class SentenceDetail:
    index: int            # sentence index within the selected range
    text: str
    start: float
    end: float
    accuracy: float       # 0-100
    fluency: float        # 0-100
    learner_start: float  # seconds into the learner's (untrimmed) recording
    learner_end: float
    words: list[WordDetail] = field(default_factory=list)


def _sec_to_frame(t: float) -> int:
    return int(round(t * FRAME_RATE_HZ))


def _path_slice_stats(dtw: DTWResult, f0: int, f1: int):
    """Return (mean_cost, ref_frames, learner_span, learner_min, learner_max)
    for path entries whose reference frame index is within [f0, f1)."""
    path = dtw.path
    costs = dtw.path_costs
    if path.shape[0] == 0 or f1 <= f0:
        return None
    mask = (path[:, 0] >= f0) & (path[:, 0] < f1)
    if not mask.any():
        return None
    sel_costs = costs[mask]
    learner_idx = path[mask, 1]
    learner_min = int(learner_idx.min())
    learner_max = int(learner_idx.max())
    learner_span = learner_max - learner_min + 1
    return float(sel_costs.mean()), int(f1 - f0), learner_span, learner_min, learner_max


def _word_status(accuracy: float, cover_ratio: float) -> str:
    if cover_ratio < MIN_COVER_RATIO:
        return "missed"
    if accuracy >= 75:
        return "good"
    if accuracy >= 50:
        return "weak"
    return "bad"


def compute_word_details(dtw: DTWResult, words: list[dict]) -> list[WordDetail]:
    """``words``: [{word, start, end}] with clip-relative seconds."""
    out: list[WordDetail] = []
    for w in words:
        f0, f1 = _sec_to_frame(w["start"]), _sec_to_frame(w["end"])
        f1 = max(f1, f0 + 1)
        stats = _path_slice_stats(dtw, f0, f1)
        if stats is None:
            out.append(WordDetail(w["word"], w["start"], w["end"], 0.0, "missed"))
            continue
        mean_cost, ref_frames, learner_span, _lmin, _lmax = stats
        accuracy = _lin_map(mean_cost, ACC_DIST_GOOD, ACC_DIST_BAD)
        cover_ratio = learner_span / max(ref_frames, 1)
        status = _word_status(accuracy, cover_ratio)
        out.append(
            WordDetail(
                word=w["word"],
                start=w["start"],
                end=w["end"],
                accuracy=round(accuracy, 1),
                status=status,
            )
        )
    return out


def compute_sentence_details(
    dtw: DTWResult, sentences: list[dict], learner_offset: float = 0.0
) -> list[SentenceDetail]:
    """``sentences``: [{index, text, start, end, words:[...]}] clip-relative.

    ``learner_offset``: seconds of leading silence trimmed off the learner
    recording before alignment. The per-sentence learner spans returned here are
    shifted by this offset so they index into the *original* (untrimmed) learner
    upload the frontend holds — letting it replay each sentence of the learner's
    own audio.
    """
    details: list[SentenceDetail] = []
    for si, sent in enumerate(sentences):
        f0, f1 = _sec_to_frame(sent["start"]), _sec_to_frame(sent["end"])
        f1 = max(f1, f0 + 1)
        stats = _path_slice_stats(dtw, f0, f1)
        learner_start = learner_end = 0.0
        if stats is None:
            acc = fluency = 0.0
        else:
            mean_cost, ref_frames, learner_span, lmin, lmax = stats
            acc = _lin_map(mean_cost, ACC_DIST_GOOD, ACC_DIST_BAD)
            # fluency: how close the learner's duration for this sentence is to
            # the reference's (1.0 == same pace)
            ratio = learner_span / max(ref_frames, 1)
            fluency = max(0.0, 100.0 * (1.0 - min(abs(np.log(ratio + 1e-8)), 1.0)))
            learner_start = lmin / FRAME_RATE_HZ + learner_offset
            learner_end = (lmax + 1) / FRAME_RATE_HZ + learner_offset
        words = compute_word_details(dtw, sent.get("words", []))
        details.append(
            SentenceDetail(
                index=si,
                text=sent["text"],
                start=round(sent["start"], 2),
                end=round(sent["end"], 2),
                accuracy=round(acc, 1),
                fluency=round(fluency, 1),
                learner_start=round(learner_start, 2),
                learner_end=round(learner_end, 2),
                words=words,
            )
        )
    return details
