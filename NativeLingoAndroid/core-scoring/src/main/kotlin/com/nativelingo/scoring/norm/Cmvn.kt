package com.nativelingo.scoring.norm

import kotlin.math.sqrt

private const val EPS = 1e-8f

/**
 * Per-utterance CMVN (cepstral mean/variance normalisation) over the time axis
 * — the speaker-factor removal that makes the reverse-evaluation idea work:
 * two *different* voices reading the same text compare as similar.
 *
 * Direct port of `backend/core/speaker_norm.py`. Population std (ddof=0) to
 * match numpy's default `.std(axis=0)`.
 */
fun cmvn(emb: Array<FloatArray>): Array<FloatArray> {
    val t = emb.size
    if (t == 0) return emb
    val d = emb[0].size

    val mean = FloatArray(d)
    for (frame in emb) for (dim in 0 until d) mean[dim] += frame[dim]
    for (dim in 0 until d) mean[dim] /= t

    val std = FloatArray(d)
    for (frame in emb) for (dim in 0 until d) {
        val diff = frame[dim] - mean[dim]
        std[dim] += diff * diff
    }
    for (dim in 0 until d) std[dim] = sqrt(std[dim] / t) // ddof=0

    val out = Array(t) { FloatArray(d) }
    for (i in 0 until t) {
        val src = emb[i]
        val dst = out[i]
        for (dim in 0 until d) dst[dim] = (src[dim] - mean[dim]) / (std[dim] + EPS)
    }
    return out
}

/** Normalise both sequences independently — port of speaker_norm.normalize_pair. */
fun normalizePair(ref: Array<FloatArray>, learner: Array<FloatArray>) =
    cmvn(ref) to cmvn(learner)
