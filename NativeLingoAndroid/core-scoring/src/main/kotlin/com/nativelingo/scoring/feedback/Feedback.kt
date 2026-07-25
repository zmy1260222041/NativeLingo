package com.nativelingo.scoring.feedback

import com.nativelingo.scoring.score.TrackBResult
import kotlin.math.round

/**
 * Feedback layer (Track C, rule-based) — port of `backend/core/feedback.py` (FR-9).
 *
 * Per the design, **the LLM does not score** — scoring comes from the objective
 * Track B + prosody metrics. This layer only translates those structured metrics
 * into human-readable teaching feedback.
 *
 * On macOS an `llm_hook` slot exists for later swapping in a local Audio-LLM.
 * On Android that hook stays a no-op: NFR-1 says nothing leaves the device, so
 * only a *local* model could ever fill it. The rule engine below is the shipped
 * behaviour, and it is deterministic — hence exactly testable against the golden.
 */

/** The Track-A prosody comparison inputs this layer consumes. */
data class ProsodySummary(
    val notes: List<String>,
    val intonationMatch: Float = 0f,
    val pauseMatch: Float = 0f,
    val referenceF0Std: Float = 0f,
    val learnerF0Std: Float = 0f,
    val referencePauses: Int = 0,
    val learnerPauses: Int = 0,
)

data class FeedbackPayload(
    val overallScore: Float,
    val overallBand: String,
    val accuracy: Float,
    val fluency: Float,
    val speechRateRatio: Float,
    val tips: List<String>,
)

internal fun overallBand(score: Float): String = when {
    score >= 90f -> "excellent"
    score >= 75f -> "good"
    score >= 60f -> "fair"
    else -> "needs work"
}

/**
 * Port of feedback.generate_feedback. `prosody` may be null (Track A
 * unavailable), matching the Python default.
 */
fun generateFeedback(trackB: TrackBResult, prosody: ProsodySummary? = null): FeedbackPayload {
    val tips = ArrayList<String>()

    // --- accuracy ---
    val acc = trackB.accuracy
    if (acc < 60f) {
        tips.add(
            "Several sounds differ noticeably from the reference. Slow down and " +
                "focus on matching each word's pronunciation."
        )
    } else if (acc < 80f) {
        tips.add(
            "Most of your pronunciation matches. A few spots drift from the " +
                "reference — review the highlighted regions."
        )
    }

    // localized accuracy problems
    if (trackB.problems.isNotEmpty()) {
        val spots = trackB.problems.take(4).joinToString(", ") {
            "${fmt1(it.refStartS)}-${fmt1(it.refEndS)}s"
        }
        tips.add("Focus on these moments where you diverged most: $spots.")
    }

    // --- fluency / rate ---
    val rate = trackB.speechRateRatio
    if (rate > 1.25f) {
        tips.add(
            "You spoke noticeably slower than the reference (~${fmt2(rate)}x the " +
                "duration). Try to keep the rhythm closer to the original."
        )
    } else if (rate < 0.8f) {
        tips.add(
            "You spoke faster than the reference (~${fmt2(rate)}x the duration). " +
                "Slowing down a little will improve clarity."
        )
    }
    if (trackB.fluency < 70f) {
        tips.add(
            "Your timing wandered from the reference's rhythm. Practise matching " +
                "the pacing, not just the words."
        )
    }

    // --- prosody (Track A) ---
    if (prosody != null) {
        if ("intonation_flat" in prosody.notes) {
            tips.add(
                "Your intonation is flatter than the reference. Add more pitch " +
                    "movement to sound natural and expressive."
            )
        }
        if ("too_many_pauses" in prosody.notes || "choppy" in prosody.notes) {
            tips.add(
                "You paused more than the reference, which makes speech sound " +
                    "choppy. Aim for smoother, connected phrases."
            )
        }
    }

    if (tips.isEmpty()) {
        tips.add("Great job — your read closely matches the reference. Keep it up!")
    }

    val overall = round1((trackB.accuracy + trackB.fluency) / 2f)
    return FeedbackPayload(
        overallScore = overall,
        overallBand = overallBand(overall),
        accuracy = trackB.accuracy,
        fluency = trackB.fluency,
        speechRateRatio = trackB.speechRateRatio,
        tips = tips,
    )
}

private fun round1(x: Float): Float = round(x * 10f) / 10f

/** Python's f"{x:.1f}" — round-half-even, one decimal. */
private fun fmt1(x: Float): String {
    val r = Math.rint(x.toDouble() * 10.0) / 10.0
    return String.format("%.1f", r)
}

/** Python's f"{x:.2f}". */
private fun fmt2(x: Float): String {
    val r = Math.rint(x.toDouble() * 100.0) / 100.0
    return String.format("%.2f", r)
}
