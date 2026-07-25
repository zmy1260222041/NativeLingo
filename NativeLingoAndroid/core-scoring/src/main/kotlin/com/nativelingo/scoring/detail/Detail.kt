package com.nativelingo.scoring.detail

import com.nativelingo.scoring.score.Calibration
import kotlin.math.max
import kotlin.math.round

/**
 * Per-word breakdown (FR-6 定位) — port of `backend/core/detail.py`.
 * Projects the Track-B DTW path onto the reference transcript's word grid:
 * each word's mean aligned cosine cost → accuracy → good/weak/bad/missed.
 * No extra model; pure projection of the existing alignment.
 */
data class WordSpan(val word: String, val start: Float, val end: Float)
data class WordDetail(
    val word: String, val start: Float, val end: Float,
    val accuracy: Float, val status: String,
)

internal const val DETAIL_FRAME_RATE_HZ = 50.0f // ssl_encoder.FRAME_RATE_HZ
private const val MIN_COVER_RATIO = 0.35f

private class SliceStat(
    val meanCost: Float, val refFrames: Int,
    val learnerSpan: Int, val learnerMin: Int, val learnerMax: Int,
)

private fun secToFrame(t: Float): Int = round(t * DETAIL_FRAME_RATE_HZ).toInt()

/** Mean cost + learner-frame span for path entries whose ref frame is in [f0, f1). */
private fun pathSliceStats(path: Array<IntArray>, costs: FloatArray, f0: Int, f1: Int): SliceStat? {
    if (path.isEmpty() || f1 <= f0) return null
    var sum = 0.0
    var count = 0
    var lmin = Int.MAX_VALUE
    var lmax = Int.MIN_VALUE
    for (k in path.indices) {
        val rf = path[k][0]
        if (rf >= f0 && rf < f1) {
            sum += costs[k]
            count++
            val lf = path[k][1]
            if (lf < lmin) lmin = lf
            if (lf > lmax) lmax = lf
        }
    }
    if (count == 0) return null
    return SliceStat((sum / count).toFloat(), f1 - f0, lmax - lmin + 1, lmin, lmax)
}

private fun wordStatus(accuracy: Float, coverRatio: Float): String = when {
    coverRatio < MIN_COVER_RATIO -> "missed"
    accuracy >= 75f -> "good"
    accuracy >= 50f -> "weak"
    else -> "bad"
}

/** Port of detail.compute_word_details. */
fun computeWordDetails(
    path: Array<IntArray>,
    pathCosts: FloatArray,
    words: List<WordSpan>,
    calibration: Calibration,
): List<WordDetail> {
    val out = ArrayList<WordDetail>(words.size)
    for (w in words) {
        val f0 = secToFrame(w.start)
        val f1 = max(secToFrame(w.end), f0 + 1)
        val s = pathSliceStats(path, pathCosts, f0, f1)
        if (s == null) {
            out.add(WordDetail(w.word, w.start, w.end, 0f, "missed"))
            continue
        }
        val acc = calibration.accuracyFromCost(s.meanCost)
        val coverRatio = s.learnerSpan.toFloat() / max(s.refFrames, 1)
        out.add(WordDetail(w.word, w.start, w.end, round1(acc), wordStatus(acc, coverRatio)))
    }
    return out
}

private fun round1(x: Float): Float = round(x * 10f) / 10f
