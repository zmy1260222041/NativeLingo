"""Track B scoring: turn the DTW alignment into accuracy / fluency scores and
localized problem regions.

Accuracy  <- per-frame cosine distance along the aligned path (content match).
Fluency   <- warping-path geometry (timing / rhythm) + speech-rate and pause
             features.

Score mapping (v1.2): the hand-set linear thresholds were the weakest link of
v1.x, so both mappings are now *calibrated* on speechocean762 (learner audio +
human accuracy/fluency scores; references synthesised with macOS `say`):

* accuracy: isotonic regression  mean path cost -> human accuracy (0-100)
* fluency:  linear regression on [path deviation, |log rate ratio|,
            pauses/sec, pause-time ratio] -> human fluency (0-100)

The fitted parameters ship in ``calibration.json`` next to this file. If it is
absent the code falls back to the v1.1 hand-set transforms (minus the
rate/fluency double-count, which was removed per the roadmap).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import numpy as np

from .align import DTWResult
from .ssl_encoder import FRAME_RATE_HZ

# --- fallback (uncalibrated) mapping constants --------------------------------
# Cosine distance along the path is ~0 for identical speech and grows with
# divergence. Only used when calibration.json is missing.
ACC_DIST_GOOD = 0.10   # <= this cosine distance counts as essentially perfect
ACC_DIST_BAD = 0.55    # >= this counts as ~0 accuracy
# Per-frame accuracy below this is flagged as a problem region.
PROBLEM_FRAME_ACCURACY = 45.0
# Uncalibrated fallback: raw per-frame cost above this flags a problem region.
PROBLEM_DIST_THRESHOLD = 0.40
MIN_PROBLEM_FRAMES = 5  # >= 100 ms, to avoid flagging single-frame blips

_CALIB_PATH = os.path.join(os.path.dirname(__file__), "calibration.json")
_calib: dict | None | bool = None  # False = tried and missing


def load_calibration() -> dict | None:
    """Lazy-load the fitted calibration table (None if not shipped/found)."""
    global _calib
    if _calib is None:
        try:
            with open(_CALIB_PATH) as f:
                _calib = json.load(f)
        except Exception:  # noqa: BLE001 - any failure => uncalibrated mode
            _calib = False
    return _calib or None


def accuracy_from_cost(cost: float) -> float:
    """Map a mean DTW cosine distance to a calibrated 0-100 accuracy score."""
    calib = load_calibration()
    if calib is not None:
        iso = calib["accuracy_isotonic"]
        return float(np.clip(np.interp(cost, iso["x"], iso["y"]), 0.0, 100.0))
    return _lin_map(cost, ACC_DIST_GOOD, ACC_DIST_BAD)


def fluency_from_features(
    path_dev: float, rate_ratio: float, pause_per_s: float, pause_ratio: float
) -> float:
    """Calibrated 0-100 fluency from interpretable timing features.

    v1.1 added a global speech-rate penalty on top of the path-deviation term;
    both measure the same thing (the ideal diagonal already absorbs the global
    rate), so the rate penalty double-counted. The calibrated mapping is a
    monotone isotonic GAM over [path_dev, |log rate ratio|, pause_ratio]:
    monotone in every feature by construction, so more deviation / rate
    mismatch / pausing can never *raise* the score (plain OLS flipped signs
    under multicollinearity). ``pause_per_s`` is accepted for API stability
    but was not informative at utterance level and is unused by the GAM.
    """
    calib = load_calibration()
    if calib is not None:
        values = {
            "path_dev": path_dev,
            "lograte": abs(np.log(max(rate_ratio, 1e-3))),
            "pause_ratio": pause_ratio,
        }
        score = 0.0
        for comp in calib["fluency_gam"]["components"]:
            v = values[comp["feature"]]
            score += comp["weight"] * float(
                np.clip(np.interp(v, comp["x"], comp["y"]), 0.0, 100.0)
            )
        return float(np.clip(score, 0.0, 100.0))
    # fallback: path geometry only, no double-counted rate penalty
    return max(0.0, 100.0 * (1.0 - path_dev / 0.15))


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
    return accuracy_from_cost(dtw.normalized_cost)


def score_fluency(
    dtw: DTWResult,
    ref_len: int,
    learner_len: int,
    pause_per_s: float = 0.0,
    pause_ratio: float = 0.0,
) -> tuple[float, float]:
    """Fluency from warping-path geometry + rate/pause features.

    A perfectly steady learner traces a straight line of slope learner_len/ref_len.
    We measure the mean absolute deviation of the actual path from that ideal
    line; more deviation = more local stretching/compressing/pausing = less
    fluent. The overall speech-rate ratio is reported (and feeds the calibrated
    fluency regression as a feature rather than a second penalty).
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

    fluency = fluency_from_features(norm_dev, speech_rate_ratio, pause_per_s, pause_ratio)
    return float(fluency), float(speech_rate_ratio)


def find_problem_regions(dtw: DTWResult) -> list[ProblemRegion]:
    """Group consecutive high-distance aligned frames into problem regions,
    expressed in reference-audio seconds so the UI can highlight them."""
    path = dtw.path
    costs = dtw.path_costs
    if path.shape[0] == 0:
        return []

    calibrated = load_calibration() is not None

    def is_problem(c: float) -> bool:
        if calibrated:
            return accuracy_from_cost(c) < PROBLEM_FRAME_ACCURACY
        return c >= PROBLEM_DIST_THRESHOLD

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
        if is_problem(float(costs[k])):
            if run_start is None:
                run_start = k
            run_costs.append(float(costs[k]))
        else:
            flush(k - 1 if k > 0 else 0)
    flush(path.shape[0] - 1)
    return regions


def score_track_b(
    dtw: DTWResult,
    ref_len: int,
    learner_len: int,
    pause_per_s: float = 0.0,
    pause_ratio: float = 0.0,
) -> TrackBResult:
    accuracy = score_accuracy(dtw)
    fluency, rate = score_fluency(dtw, ref_len, learner_len, pause_per_s, pause_ratio)
    problems = find_problem_regions(dtw)
    return TrackBResult(
        accuracy=round(accuracy, 1),
        fluency=round(fluency, 1),
        speech_rate_ratio=round(rate, 3),
        problems=problems,
        raw_path_cost=round(dtw.normalized_cost, 4),
    )
