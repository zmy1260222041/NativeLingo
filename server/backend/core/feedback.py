"""Feedback layer (Track C, MVP rule-based).

Per the design, the LLM does NOT score — scoring comes from the objective
Track B + prosody metrics. This layer translates those structured metrics into
human-readable teaching feedback.

For the MVP this is a deterministic rule engine (no model download, instant,
reproducible). ``generate_feedback`` returns plain guidance strings; an
``llm_hook`` slot is left for later swapping in a local Audio-LLM (Qwen2-Audio)
that rephrases these into richer, personalised coaching.
"""
from __future__ import annotations

from typing import Callable

from .score_b import TrackBResult
from .prosody import ProsodyComparison


def _overall_band(score: float) -> str:
    if score >= 90:
        return "excellent"
    if score >= 75:
        return "good"
    if score >= 60:
        return "fair"
    return "needs work"


def generate_feedback(
    track_b: TrackBResult,
    prosody: ProsodyComparison | None = None,
    llm_hook: Callable[[dict], str] | None = None,
) -> dict:
    """Build the feedback payload from objective metrics.

    Returns a dict with an overall summary, per-dimension scores, and a list of
    actionable tips. If ``llm_hook`` is provided it receives the assembled
    metrics dict and may return a richer natural-language coaching string.
    """
    tips: list[str] = []

    # --- accuracy ---
    acc = track_b.accuracy
    if acc < 60:
        tips.append(
            "Several sounds differ noticeably from the reference. Slow down and "
            "focus on matching each word's pronunciation."
        )
    elif acc < 80:
        tips.append(
            "Most of your pronunciation matches. A few spots drift from the "
            "reference — review the highlighted regions."
        )

    # localized accuracy problems
    if track_b.problems:
        spots = ", ".join(
            f"{p.ref_start_s:.1f}-{p.ref_end_s:.1f}s" for p in track_b.problems[:4]
        )
        tips.append(f"Focus on these moments where you diverged most: {spots}.")

    # --- fluency / rate ---
    rate = track_b.speech_rate_ratio
    if rate > 1.25:
        tips.append(
            f"You spoke noticeably slower than the reference (~{rate:.2f}x the "
            "duration). Try to keep the rhythm closer to the original."
        )
    elif rate < 0.8:
        tips.append(
            f"You spoke faster than the reference (~{rate:.2f}x the duration). "
            "Slowing down a little will improve clarity."
        )
    if track_b.fluency < 70:
        tips.append(
            "Your timing wandered from the reference's rhythm. Practise matching "
            "the pacing, not just the words."
        )

    # --- prosody (Track A) ---
    if prosody is not None:
        if "intonation_flat" in prosody.notes:
            tips.append(
                "Your intonation is flatter than the reference. Add more pitch "
                "movement to sound natural and expressive."
            )
        if "too_many_pauses" in prosody.notes or "choppy" in prosody.notes:
            tips.append(
                "You paused more than the reference, which makes speech sound "
                "choppy. Aim for smoother, connected phrases."
            )

    if not tips:
        tips.append("Great job — your read closely matches the reference. Keep it up!")

    overall = round((track_b.accuracy + track_b.fluency) / 2.0, 1)
    payload = {
        "overall_score": overall,
        "overall_band": _overall_band(overall),
        "accuracy": track_b.accuracy,
        "fluency": track_b.fluency,
        "speech_rate_ratio": track_b.speech_rate_ratio,
        "tips": tips,
        "problem_regions": [
            {
                "start_s": p.ref_start_s,
                "end_s": p.ref_end_s,
                "severity": p.severity,
                "kind": p.kind,
            }
            for p in track_b.problems
        ],
    }
    if prosody is not None:
        payload["prosody"] = {
            "intonation_match": prosody.intonation_match,
            "pause_match": prosody.pause_match,
            "reference_f0_std": prosody.reference.f0_std,
            "learner_f0_std": prosody.learner.f0_std,
            "reference_pauses": prosody.reference.num_pauses,
            "learner_pauses": prosody.learner.num_pauses,
        }

    if llm_hook is not None:
        try:
            payload["coaching"] = llm_hook(payload)
        except Exception as exc:  # noqa: BLE001 - never let LLM break scoring
            payload["coaching_error"] = str(exc)

    return payload
