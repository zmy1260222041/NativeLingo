package com.nativelingo.scoring.score

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.round

/** Frame rate of the SSL encoder's output (ssl_encoder.FRAME_RATE_HZ, 20ms hop). */
const val FRAME_RATE_HZ = 50.0f

/** Per-frame accuracy below this flags a problem region (score_b.PROBLEM_FRAME_ACCURACY). */
private const val PROBLEM_FRAME_ACCURACY = 45.0f
/** >= 100ms, so single-frame blips aren't reported (score_b.MIN_PROBLEM_FRAMES). */
private const val MIN_PROBLEM_FRAMES = 5

/** A localized stretch where the learner diverged, in reference-audio seconds. */
data class ProblemRegion(
    val refStartS: Float,
    val refEndS: Float,
    val severity: Float,  // mean cosine distance in the region
    val kind: String,     // "accuracy" | "pause" | "rushed"
)

/** Port of score_b.TrackBResult. */
data class TrackBResult(
    val accuracy: Float,
    val fluency: Float,
    val speechRateRatio: Float,
    val problems: List<ProblemRegion>,
    val rawPathCost: Float,
)

/**
 * Port of `score_b.find_problem_regions`: group consecutive high-distance
 * aligned frames into regions the UI can highlight.
 *
 * The macOS fallback (uncalibrated) branch is intentionally NOT ported —
 * calibration.json always ships with the app (NFR-Q1: the mapping is data, and
 * the app is useless without it), so the calibrated branch is the only path.
 */
fun findProblemRegions(
    path: Array<IntArray>,
    pathCosts: FloatArray,
    calibration: Calibration,
): List<ProblemRegion> {
    if (path.isEmpty()) return emptyList()
    val regions = ArrayList<ProblemRegion>()
    var runStart = -1
    var runSum = 0.0
    var runLen = 0

    fun flush(endK: Int) {
        if (runStart < 0) return
        if (runLen >= MIN_PROBLEM_FRAMES) {
            regions.add(
                ProblemRegion(
                    refStartS = round2(path[runStart][0] / FRAME_RATE_HZ),
                    refEndS = round2(path[endK][0] / FRAME_RATE_HZ),
                    severity = round3((runSum / runLen).toFloat()),
                    kind = "accuracy",
                )
            )
        }
        runStart = -1; runSum = 0.0; runLen = 0
    }

    for (k in path.indices) {
        val c = pathCosts[k]
        if (calibration.accuracyFromCost(c) < PROBLEM_FRAME_ACCURACY) {
            if (runStart < 0) runStart = k
            runSum += c; runLen++
        } else {
            flush(if (k > 0) k - 1 else 0)
        }
    }
    flush(path.size - 1)
    return regions
}

/** Port of score_b.score_track_b — the full FR-4/FR-5 Track-B result. */
fun scoreTrackB(
    path: Array<IntArray>,
    pathCosts: FloatArray,
    normalizedCost: Float,
    refLen: Int,
    learnerLen: Int,
    pausePerS: Float,
    pauseRatio: Float,
    calibration: Calibration,
): TrackBResult {
    val accuracy = calibration.accuracyFromCost(normalizedCost)
    val (fluency, rate) = scoreFluency(path, refLen, learnerLen, pausePerS, pauseRatio, calibration)
    return TrackBResult(
        accuracy = round1(accuracy),
        fluency = round1(fluency),
        speechRateRatio = round3(rate),
        problems = findProblemRegions(path, pathCosts, calibration),
        rawPathCost = round4(normalizedCost),
    )
}

private fun round1(x: Float) = round(x * 10f) / 10f
private fun round2(x: Float) = round(x * 100f) / 100f
private fun round3(x: Float) = round(x * 1000f) / 1000f
private fun round4(x: Float) = round(x * 10000f) / 10000f

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
