package com.nativelingo.scoring.align

import kotlin.math.abs
import kotlin.math.round
import kotlin.math.sqrt

/**
 * Banded (Sakoe-Chiba) Dynamic Time Warping of two embedding sequences.
 *
 * Direct port of `backend/core/align.py` (band_frac = 0.2, float32 accumulate,
 * cosine-distance cost, numpy-argmin tie-break on backtrack). The path's mean
 * cosine cost is the accuracy basis; the path shape feeds fluency.
 */
data class DtwResult(
    val path: Array<IntArray>,   // (K, 2) aligned (refIdx, learnerIdx)
    val pathCosts: FloatArray,   // (K,) cosine distance at each aligned pair
    val normalizedCost: Float,   // mean cost along the path -> accuracy basis
)

private const val EPS = 1e-8f
private const val INF = 1e9f

private fun normRows(a: Array<FloatArray>): FloatArray {
    val out = FloatArray(a.size)
    for (i in a.indices) {
        var s = 0f
        for (v in a[i]) s += v * v
        out[i] = sqrt(s) + EPS
    }
    return out
}

/** Pairwise cosine distance (1 - cosine similarity) between rows of a (n,d) and b (m,d). */
fun cosineDistanceMatrix(a: Array<FloatArray>, b: Array<FloatArray>): Array<FloatArray> {
    val aN = normRows(a)
    val bN = normRows(b)
    val out = Array(a.size) { FloatArray(b.size) }
    for (i in a.indices) {
        val ai = a[i]
        val an = aN[i]
        val row = out[i]
        for (j in b.indices) {
            val bj = b[j]
            var dot = 0f
            for (dim in ai.indices) dot += ai[dim] * bj[dim]
            row[j] = 1f - dot / (an * bN[j])
        }
    }
    return out
}

/** Align ``learner`` to ``ref`` via banded DTW. Port of align.dtw_align. */
fun dtwAlign(ref: Array<FloatArray>, learner: Array<FloatArray>, bandFrac: Float = 0.2f): DtwResult {
    val n = ref.size
    val m = learner.size
    if (n == 0 || m == 0) return DtwResult(emptyArray(), FloatArray(0), 1f)

    val cost = cosineDistanceMatrix(ref, learner)
    val band = maxOf((bandFrac * maxOf(n, m)).toInt(), abs(n - m) + 1)
    val stride = m + 1
    val acc = FloatArray((n + 1) * stride) { INF }
    acc[0] = 0f

    for (i in 1..n) {
        val jCenter = round(i.toFloat() * m.toFloat() / n.toFloat()).toInt()
        val jLo = maxOf(1, jCenter - band)
        val jHi = minOf(m, jCenter + band)
        for (j in jLo..jHi) {
            val up = acc[(i - 1) * stride + j]
            val left = acc[i * stride + (j - 1)]
            val diag = acc[(i - 1) * stride + (j - 1)]
            var best = up
            if (left < best) best = left
            if (diag < best) best = diag
            acc[i * stride + j] = cost[i - 1][j - 1] + best
        }
    }

    // backtrack — numpy argmin over (diag, up, left) with first-min tie-break
    val path = mutableListOf<IntArray>()
    var i = n
    var j = m
    while (i > 0 && j > 0) {
        path.add(intArrayOf(i - 1, j - 1))
        val diag = acc[(i - 1) * stride + (j - 1)]
        val up = acc[(i - 1) * stride + j]
        val left = acc[i * stride + (j - 1)]
        when {
            diag <= up && diag <= left -> { i--; j-- }
            up <= left -> i--
            else -> j--
        }
    }
    path.reverse()

    val pathArr = path.toTypedArray()
    val costs = FloatArray(pathArr.size) { k -> cost[pathArr[k][0]][pathArr[k][1]] }
    val normCost = if (costs.isEmpty()) 1f else costs.sum() / costs.size
    return DtwResult(pathArr, costs, normCost)
}
