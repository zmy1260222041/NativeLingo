package com.nativelingo.align

import com.nativelingo.scoring.viterbi.ctcAlign

/**
 * Character-level forced alignment — the Android port of `backend/core/forced_align.py`
 * (FR-2 word boundaries; FR-6/FR-7/FR-8 all consume the spans it produces).
 *
 * Why forced alignment rather than ASR timestamps: Whisper's word timestamps come
 * from decoder cross-attention and are only approximate — they clip word tails and
 * collapse short words. Here the transcript is *known*, so we Viterbi-decode the
 * monotonic alignment of its characters to the frames at ~20 ms. A mispronounced
 * word still maps to the word it *should* be, which is exactly what a shadowing
 * evaluator needs.
 *
 * The Viterbi itself is [ctcAlign] in :core-scoring — shared with phoneme MDD and
 * verified frame-for-frame against torchaudio (Gate B / R-6).
 */
object MmsDict {
    const val BLANK = 0

    /** `MMS_FA.get_dict()` — blank, 26 letters, apostrophe, and the star wildcard. */
    val TOKENS: Map<Char, Int> = mapOf(
        '-' to 0, 'a' to 1, 'i' to 2, 'e' to 3, 'n' to 4, 'o' to 5, 'u' to 6,
        't' to 7, 's' to 8, 'r' to 9, 'm' to 10, 'k' to 11, 'l' to 12, 'd' to 13,
        'g' to 14, 'h' to 15, 'y' to 16, 'b' to 17, 'p' to 18, 'w' to 19,
        'c' to 20, 'v' to 21, 'j' to 22, 'z' to 23, 'f' to 24, '\'' to 25,
        'q' to 26, 'x' to 27, '*' to 28,
    )
}

const val ALIGN_SR = 16000

/** A word's span in seconds, or null where the word could not be aligned. */
data class AlignedSpan(val startS: Float, val endS: Float)

/**
 * `_clean` — strip everything outside `[a-z']` after lowercasing. Words that
 * clean to empty (a bare number, say) get no span and are skipped, exactly as
 * on macOS, so callers can fall back for those.
 *
 * Uses Kotlin's locale-independent [lowercase]; Java's default-locale variant
 * would map 'I' to a dotless ı under a Turkish locale and then drop it.
 */
fun cleanWord(word: String): String =
    buildString { for (c in word.lowercase()) if (c in 'a'..'z' || c == '\'') append(c) }

/**
 * Align an ordered word sequence to a precomputed emission.
 *
 * @param emission (T, V) log-prob frames from [MmsEmitter].
 * @param wavSamples the source waveform length — seconds-per-frame is derived
 *   from it rather than hardcoded to 0.02, so the mapping stays correct for any
 *   model stride (macOS does the same).
 * @return a list parallel to [words]; null entries are words with no alignment.
 *   Returns null entirely when alignment is impossible, so callers can fall back.
 */
fun alignWords(
    words: List<String>,
    emission: Array<FloatArray>,
    wavSamples: Int,
): List<AlignedSpan?>? {
    if (words.isEmpty() || emission.isEmpty() || wavSamples <= 0) return null
    val nframes = emission.size
    val cleaned = words.map(::cleanWord)
    val keepIdx = cleaned.indices.filter { cleaned[it].isNotEmpty() }
    if (keepIdx.isEmpty()) return null

    // one flat character sequence across all kept words, then unflatten by
    // word length — torchaudio's aligner does exactly this, and it matters:
    // aligning words independently would let their frame ranges overlap.
    val charIds = ArrayList<Int>()
    for (i in keepIdx) {
        for (c in cleaned[i]) {
            charIds.add(MmsDict.TOKENS[c] ?: return null)
        }
    }

    val logProbs = Array(nframes) { t ->
        val row = emission[t]
        DoubleArray(row.size) { row[it].toDouble() }
    }
    val result = ctcAlign(logProbs, charIds.toIntArray(), MmsDict.BLANK)

    // ext position 2k+1 holds the k-th character; a character with no span in
    // the backtrack was never visited and the word is left unaligned.
    val byChar = HashMap<Int, IntArray>(charIds.size * 2)
    for (s in result.spans) {
        if (s.extPos % 2 == 1) byChar[(s.extPos - 1) / 2] = intArrayOf(s.firstFrame, s.lastFrame)
    }

    val spf = (wavSamples.toDouble() / ALIGN_SR) / nframes
    val out = arrayOfNulls<AlignedSpan>(words.size)
    var ci = 0
    for (i in keepIdx) {
        val n = cleaned[i].length
        val first = byChar[ci]
        val last = byChar[ci + n - 1]
        ci += n
        if (first == null || last == null) continue
        // torchaudio's TokenSpan.end is exclusive (= lastFrame + 1), and macOS
        // then adds one more frame of tail: end = (f1 + 1) * spf. Reproduced
        // verbatim — the golden word spans encode this, and FR-8 replay seeks
        // to them, so "more correct" here would just desync from macOS.
        val f0 = first[0]
        val f1 = last[1] + 1
        out[i] = AlignedSpan(round3(f0 * spf), round3((f1 + 1) * spf))
    }
    return out.toList()
}

/** Python's `round(x, 3)` — round-half-even, as used by `align_words`. */
private fun round3(x: Double): Float = (Math.rint(x * 1000.0) / 1000.0).toFloat()

/**
 * Convenience: emission + alignment in one call.
 *
 * Mirrors macOS's degrade-gracefully contract — alignment is optional and must
 * never break analysis, so a failure returns null instead of propagating.
 */
class ForcedAligner(private val emitter: MmsEmitter) {
    fun align(words: List<String>, wav: FloatArray): List<AlignedSpan?>? = try {
        if (wav.isEmpty()) null else alignWords(words, emitter.emission(wav), wav.size)
    } catch (_: Exception) {
        null
    }
}
