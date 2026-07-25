package com.nativelingo.scoring.viterbi

import kotlin.math.max

/**
 * CTC forced alignment via the blank-extended Viterbi — shared by MMS forced
 * alignment (Gate B) and phoneme MDD scoring (Gate C). This is the canonical
 * CTC forced-align DP (Graves 2012; Hannun 2014) that both torchaudio's
 * `functional.forced_align` and `backend/core/phoneme.py:_viterbi_align`
 * implement; ported from the latter verbatim.
 *
 * `emission[t]` = V-dim log-prob vector at frame t. `seqIds` = target token
 * sequence. Returns the mean log-prob/frame and the frame range each position
 * of the blank-extended sequence aligned to. Odd ext positions are the real
 * tokens: ext position `2k+1` ↔ `seqIds[k]`.
 */
data class CtcSpan(val extPos: Int, val firstFrame: Int, val lastFrame: Int)
data class CtcAlignResult(val meanLogprob: Double, val spans: List<CtcSpan>)

private const val NEG = -1e30

fun ctcAlign(emission: Array<DoubleArray>, seqIds: IntArray, blank: Int = 0): CtcAlignResult {
    val t = emission.size
    if (t == 0 || seqIds.isEmpty()) return CtcAlignResult(0.0, emptyList())

    // blank-extended sequence: [blank, s0, blank, s1, blank, …, s_{n-1}, blank]
    val ext = IntArray(seqIds.size * 2 + 1)
    ext[0] = blank
    for (i in seqIds.indices) {
        ext[2 * i + 1] = seqIds[i]
        ext[2 * i + 2] = blank
    }
    val s = ext.size

    val dp = Array(t) { DoubleArray(s) { NEG } }
    val bp = Array(t) { IntArray(s) { -1 } }
    dp[0][0] = emission[0][blank]
    if (s > 1) { dp[0][1] = emission[0][ext[1]]; bp[0][1] = 0 }

    for (ti in 1 until t) {
        val row = emission[ti]
        val prev = dp[ti - 1]
        val cur = dp[ti]
        val bpt = bp[ti]
        for (si in 0 until s) {
            var bestVal = prev[si]
            var bestSrc = si
            if (si - 1 >= 0 && prev[si - 1] > bestVal) { bestVal = prev[si - 1]; bestSrc = si - 1 }
            // skip-over-blank transition — only for real tokens that differ from
            // the token two positions back (CTC forbids skipping repeats).
            if (si - 2 >= 0 && ext[si] != blank && ext[si] != ext[si - 2] && prev[si - 2] > bestVal) {
                bestVal = prev[si - 2]; bestSrc = si - 2
            }
            if (bestVal <= NEG) continue
            cur[si] = row[ext[si]] + bestVal
            bpt[si] = bestSrc
        }
    }

    // terminal cell: trailing blank (s-1) or the last real token (s-2)
    val last = if (dp[t - 1][s - 1] >= (if (s > 1) dp[t - 1][s - 2] else NEG)) s - 1 else s - 2
    val finalScore = dp[t - 1][last]

    // backtrack — collect frame range per ext position
    val ranges = HashMap<Int, IntArray>()
    var ti = t - 1
    var si = last
    while (ti >= 0 && si >= 0) {
        val r = ranges.getOrPut(si) { intArrayOf(ti, ti) }
        if (ti < r[0]) r[0] = ti
        if (ti > r[1]) r[1] = ti
        si = bp[ti][si]
        ti -= 1
    }
    val spans = ranges.keys.sorted().map { CtcSpan(it, ranges.getValue(it)[0], ranges.getValue(it)[1]) }
    return CtcAlignResult(finalScore / max(t, 1), spans)
}
