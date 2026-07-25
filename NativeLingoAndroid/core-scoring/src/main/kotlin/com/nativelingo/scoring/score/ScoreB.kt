package com.nativelingo.scoring.score

import kotlin.math.abs
import kotlin.math.max

/**
 * Port of `backend/core/score_b.py` score_fluency: mean absolute deviation of
 * the warping path from the constant-rate ideal line, normalised by sequence
 * length, then fed through the calibrated GAM. Returns (fluency, speechRateRatio).
 */
fun scoreFluency(
    path: Array<IntArray>,
    refLen: Int,
    learnerLen: Int,
    pausePerS: Float,
    pauseRatio: Float,
    calibration: Calibration,
): Pair<Float, Float> {
    if (path.isEmpty() || refLen == 0 || learnerLen == 0) return 0f to 1f
    val rate = learnerLen.toDouble() / refLen.toDouble()
    var sumDev = 0.0
    for (p in path) {
        val ideal = p[0] * rate
        sumDev += abs(p[1] - ideal)
    }
    val normDev = ((sumDev / path.size) / max(learnerLen, 1)).toFloat()
    val fluency = calibration.fluencyFromFeatures(normDev, rate.toFloat(), pausePerS, pauseRatio)
    return fluency to rate.toFloat()
}
