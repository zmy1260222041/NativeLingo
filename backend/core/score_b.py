"""Track B scoring: turn the DTW alignment into accuracy / fluency scores and
localized problem regions.

Accuracy  <- per-frame cosine distance along the aligned path (content match).
Fluency   <- how much the warping path deviates from a steady diagonal
             (timing / rhythm / pauses), plus an overall speech-rate ratio.

Scores are mapped to a 0-100 scale via simple, tunable transforms. These
thresholds are the obvious first-pass tuning target — they're isolated here so
they can be calibrated against Track A and labelled samples later.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .align import DTWResult
from .ssl_encoder import FRAME_RATE_HZ

# --- tunable mapping constants -------------------------------------------------
# Cosine distance along the path is ~0 for identical speech and grows with
# divergence. These map distance -> score; calibrate against labelled data.
ACC_DIST_GOOD = 0.10   # <= this cosine distance counts as essentially perfect
ACC_DIST_BAD = 0.55    # >= this counts as ~0 accuracy
# Per-frame distance above this is flagged as a problem region.
PROBLEM_DIST_THRESHOLD = 0.40
MIN_PROBLEM_FRAMES = 5  # >= 100 ms, to avoid flagging single-frame blips


@dataclass
class ProblemRegion:
    ref_start_s: float
    ref_end_s: float
    severity: float  # mean cosine distance in the region (0..~1)
    kind: str        # "accuracy" | "pause" | "rushed"


@dataclass
class TrackBResult:
    accuracy: float                       # 0-100
    fluency: float                        # 0-100
    speech_rate_ratio: float              # learner_dur / ref_dur
    problems: list[ProblemRegion] = field(default_factory=list)
    raw_path_cost: float = 0.0


def _lin_map(x: float, good: float, bad: float) -> float:
    """Map x in [good, bad] -> [100, 0], clamped."""
    if x <= good:
        return 100.0
    if x >= bad:
        return 0.0
    return float(100.0 * (bad - x) / (bad - good))


def score_accuracy(dtw: DTWResult) -> float:
    return _lin_map(dtw.normalized_cost, ACC_DIST_GOOD, ACC_DIST_BAD)


def score_fluency(dtw: DTWResult, ref_len: int, learner_len: int) -> tuple[float, float]:
    """Fluency from warping-path geometry.

    A perfectly steady learner traces a straight line of slope learner_len/ref_len.
    We measure the mean absolute deviation of the actual path from that ideal
    line; more deviation = more local stretching/compressing/pausing = less
    fluent. We also report the overall speech-rate ratio.
    """
    path = dtw.path
    if path.shape[0] == 0 or ref_len == 0 or learner_len == 0:
        return 0.0, 1.0

    speech_rate_ratio = learner_len / ref_len

    ref_idx = path[:, 0].astype("float64")
    learner_idx = path[:, 1].astype("float64")
    # ideal learner index given ref index, under constant speech rate
    ideal = ref_idx * speech_rate_ratio
    deviation = np.abs(learner_idx - ideal)
    # normalise deviation by sequence length so it's scale-free
    norm_dev = float(deviation.mean() / max(learner_len, 1))

    # map: 0 deviation -> 100, 0.15 (15% of length) -> ~0
    fluency = max(0.0, 100.0 * (1.0 - norm_dev / 0.15))

    # penalise extreme speech-rate mismatch (too fast / too slow vs reference)
    rate_penalty = min(abs(np.log(speech_rate_ratio + 1e-8)) * 40.0, 40.0)
    fluency = max(0.0, fluency - rate_penalty)
    return float(fluency), float(speech_rate_ratio)


def find_problem_regions(dtw: DTWResult) -> list[ProblemRegion]:
    """Group consecutive high-distance aligned frames into problem regions,
    expressed in reference-audio seconds so the UI can highlight them."""
    path = dtw.path
    costs = dtw.path_costs
    if path.shape[0] == 0:
        return []

    regions: list[ProblemRegion] = []
    run_start = None
    run_costs: list[float] = []

    def flush(end_k: int):
        nonlocal run_start, run_costs
        if run_start is None:
            return
        if len(run_costs) >= MIN_PROBLEM_FRAMES:
            ref_s = path[run_start, 0] / FRAME_RATE_HZ
            ref_e = path[end_k, 0] / FRAME_RATE_HZ
            regions.append(
                ProblemRegion(
                    ref_start_s=round(float(ref_s), 2),
                    ref_end_s=round(float(ref_e), 2),
                    severity=round(float(np.mean(run_costs)), 3),
                    kind="accuracy",
                )
            )
        run_start = None
        run_costs = []

    for k in range(path.shape[0]):
        if costs[k] >= PROBLEM_DIST_THRESHOLD:
            if run_start is None:
                run_start = k
            run_costs.append(float(costs[k]))
        else:
            flush(k - 1 if k > 0 else 0)
    flush(path.shape[0] - 1)
    return regions


def score_track_b(dtw: DTWResult, ref_len: int, learner_len: int) -> TrackBResult:
    accuracy = score_accuracy(dtw)
    fluency, rate = score_fluency(dtw, ref_len, learner_len)
    problems = find_problem_regions(dtw)
    return TrackBResult(
        accuracy=round(accuracy, 1),
        fluency=round(fluency, 1),
        speech_rate_ratio=round(rate, 3),
        problems=problems,
        raw_path_cost=round(dtw.normalized_cost, 4),
    )
