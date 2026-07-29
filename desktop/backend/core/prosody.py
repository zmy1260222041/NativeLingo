"""Track A (support / calibration): prosody features via Praat/Parselmouth.

Track B works in an abstract SSL latent space; Track A gives interpretable,
physically meaningful measurements (pitch, energy, pauses, speech rate) that
both (a) calibrate Track B and (b) feed concrete, human-readable feedback.

We compare learner vs reference on:
* pitch (F0) range and variation  -> intonation / expressiveness
* pause structure                 -> fluency breakdowns
* articulation rate               -> speed
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import parselmouth
from parselmouth.praat import call

from .audio_io import TARGET_SR


@dataclass
class ProsodyFeatures:
    duration_s: float
    f0_mean: float          # Hz (0 if unvoiced/unknown)
    f0_std: float           # Hz, intonation variation
    f0_range: float         # Hz, p5..p95 span
    num_pauses: int         # silent pauses > threshold
    total_pause_s: float
    articulation_rate: float  # voiced-energy proxy per second


@dataclass
class ProsodyComparison:
    reference: ProsodyFeatures
    learner: ProsodyFeatures
    intonation_match: float   # 0-100, similarity of F0 variation
    pause_match: float        # 0-100, similarity of pause behaviour
    notes: list[str] = field(default_factory=list)


def _to_sound(wav: np.ndarray) -> parselmouth.Sound:
    return parselmouth.Sound(wav.astype("float64"), sampling_frequency=TARGET_SR)


def extract_prosody(wav: np.ndarray, silence_db: float = -25.0,
                    min_pause_s: float = 0.15) -> ProsodyFeatures:
    if wav.size == 0:
        return ProsodyFeatures(0, 0, 0, 0, 0, 0.0, 0.0)

    sound = _to_sound(wav)
    duration = sound.get_total_duration()

    # --- pitch / F0 ---
    pitch = sound.to_pitch()
    f0 = pitch.selected_array["frequency"]
    voiced = f0[f0 > 0]
    if voiced.size:
        f0_mean = float(np.mean(voiced))
        f0_std = float(np.std(voiced))
        f0_range = float(np.percentile(voiced, 95) - np.percentile(voiced, 5))
    else:
        f0_mean = f0_std = f0_range = 0.0

    # --- pauses via intensity-based silence detection ---
    intensity = sound.to_intensity()
    times = intensity.xs()
    vals = intensity.values[0]
    silent = vals < (np.nanmax(vals) + silence_db) if vals.size else np.array([])
    num_pauses, total_pause = _count_pauses(times, silent, min_pause_s)

    speaking_time = max(duration - total_pause, 1e-3)
    # articulation rate proxy: voiced frames per second of speaking time
    articulation_rate = float(voiced.size / speaking_time) if voiced.size else 0.0

    return ProsodyFeatures(
        duration_s=round(duration, 3),
        f0_mean=round(f0_mean, 1),
        f0_std=round(f0_std, 1),
        f0_range=round(f0_range, 1),
        num_pauses=num_pauses,
        total_pause_s=round(total_pause, 3),
        articulation_rate=round(articulation_rate, 2),
    )


def _count_pauses(times, silent_mask, min_pause_s):
    if len(times) < 2:
        return 0, 0.0
    dt = float(times[1] - times[0])
    num = 0
    total = 0.0
    run = 0
    for s in silent_mask:
        if s:
            run += 1
        else:
            dur = run * dt
            if dur >= min_pause_s:
                num += 1
                total += dur
            run = 0
    dur = run * dt
    if dur >= min_pause_s:
        num += 1
        total += dur
    return num, total


def _similarity(a: float, b: float, scale: float) -> float:
    """100 when equal, decaying with absolute difference over ``scale``."""
    diff = abs(a - b)
    return float(max(0.0, 100.0 * (1.0 - diff / scale)))


def compare_prosody(ref_wav: np.ndarray, learner_wav: np.ndarray) -> ProsodyComparison:
    ref = extract_prosody(ref_wav)
    learner = extract_prosody(learner_wav)

    # intonation: compare F0 variation (std) — a flat learner reads monotone
    intonation_match = _similarity(ref.f0_std, learner.f0_std, scale=60.0)
    # pauses: compare total pause time
    pause_match = _similarity(ref.total_pause_s, learner.total_pause_s, scale=1.5)

    notes: list[str] = []
    if learner.f0_std < ref.f0_std * 0.6 and ref.f0_std > 0:
        notes.append("intonation_flat")
    if learner.total_pause_s > ref.total_pause_s + 0.5:
        notes.append("too_many_pauses")
    if learner.num_pauses > ref.num_pauses + 1:
        notes.append("choppy")

    return ProsodyComparison(
        reference=ref,
        learner=learner,
        intonation_match=round(intonation_match, 1),
        pause_match=round(pause_match, 1),
        notes=notes,
    )
