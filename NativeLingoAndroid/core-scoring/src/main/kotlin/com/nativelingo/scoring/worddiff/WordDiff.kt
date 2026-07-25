package com.nativelingo.scoring.worddiff

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.round
import kotlin.math.sqrt

/**
 * Word-level pronunciation difference diagnosis (逐词读法改进方向) —
 * port of `backend/core/word_diff.py` (FR-7).
 *
 * The reverse-cloning insight made concrete: hold content fixed (same words),
 * discard the speaker factor (different voice — irrelevant), and isolate the
 * *prosodic delta* on each word — where the stress sits, whether adjacent words
 * link, vowel length, pitch movement — then name that delta in words the
 * learner can act on.
 *
 * Everything here is pure Kotlin stdlib EXCEPT pitch, which is injected via
 * [PitchEstimator] — Praat's autocorrelation tracker has no bit-exact JVM
 * equivalent, so on Android it is backed by TarsosDSP YIN and on the JVM test
 * path it is [NoPitch]. The stress / duration / linking logic (the bulk of the
 * diagnosis) IS bit-portable and is asserted against the macOS golden.
 */

const val SR = 16000

// thresholds — identical to word_diff.py
private const val STRESS_POS_DELTA = 0.28f   // normalized-position gap => stress shift
private const val LINK_REF_MAX_GAP = 0.06f   // ref gap below this == words are linked
private const val LINK_EXTRA_GAP = 0.10f     // learner gap this much larger == broke it
private const val SHORT_RATIO = 0.62f        // learner/ref duration below this == clipped
private const val LONG_RATIO = 1.75f         // ... above this == dragged out
private const val PITCH_MIN_SLOPE = 12.0f    // Hz/word span for a real pitch move
private const val MIN_SPAN_S = 0.05f         // ignore spans shorter than this

/** A reference word with its status, in clip-relative seconds. */
data class RefWord(
    val si: Int, val wi: Int, val word: String,
    val start: Float, val end: Float, val status: String,
)

/** A learner word span, in learner-recording seconds. */
data class LearnerWord(val word: String, val start: Float, val end: Float)

/** Port of word_diff.WordDiff. */
data class WordDiff(
    val si: Int,
    val wi: Int,
    val word: String,
    var tip: String,
    val learnerStart: Float = 0f,
    val learnerEnd: Float = 0f,
    val tags: MutableList<String> = mutableListOf(),
)

/**
 * F0 slope over a span, in Hz across the whole span (+rising / -falling),
 * or null when there isn't enough voiced signal to judge.
 *
 * On macOS this is Praat via Parselmouth; on Android it is TarsosDSP YIN
 * (docs/android-migration.md §4). The two do NOT agree bit-for-bit, which is
 * why pitch tips are excluded from the exact-parity assertion.
 */
fun interface PitchEstimator {
    fun slopeHz(span: FloatArray): Float?
}

/** No pitch track — the diagnosis degrades to stress/duration/linking only. */
val NoPitch = PitchEstimator { null }

// --------------------------------------------------------------------------- //
// small acoustic helpers
// --------------------------------------------------------------------------- //

/** Port of word_diff._slice: seconds -> sample window, clipped to the waveform. */
internal fun slice(wav: FloatArray, start: Float, end: Float): FloatArray {
    val a = max(0, round(start * SR).toInt())
    val b = min(wav.size, round(end * SR).toInt())
    return if (b > a) wav.copyOfRange(a, b) else FloatArray(0)
}

/**
 * Short-time RMS energy envelope over a word span (25ms frame, 5ms hop).
 * Port of word_diff._rms_envelope; null if the span is too short.
 */
internal fun rmsEnvelope(span: FloatArray, frame: Float = 0.025f, hop: Float = 0.005f): FloatArray? {
    val n = span.size
    val fl = max(1, (frame * SR).toInt())
    val hp = max(1, (hop * SR).toInt())
    if (n < fl) return null
    val count = (n - fl) / hp + 1
    if (count < 3) return null
    val env = FloatArray(count)
    for (k in 0 until count) {
        val i = k * hp
        // float64 accumulate: numpy's mean is float64 even on a float32 array,
        // and these sums run over 400 samples of squared values.
        var s = 0.0
        for (t in i until i + fl) { val v = span[t].toDouble(); s += v * v }
        env[k] = sqrt(s / fl + 1e-9).toFloat()
    }
    return env
}

/**
 * Normalized position [0,1] of the loudest part of a word (its stress), or null
 * if the span is too short or too flat to judge. Port of word_diff._stress_pos.
 */
internal fun stressPos(span: FloatArray): Float? {
    var env = rmsEnvelope(span) ?: return null
    // smooth a touch to avoid picking a single spiky frame — np.convolve(mode="same")
    val k = min(5, env.size)
    if (k >= 3) env = convolveSame(env, k)
    var lo = Float.MAX_VALUE
    var hi = -Float.MAX_VALUE
    for (v in env) { if (v < lo) lo = v; if (v > hi) hi = v }
    if (hi - lo < 0.02f * (hi + 1e-6f)) return null  // essentially flat -> no clear stress
    var peak = 0
    for (i in env.indices) if (env[i] > env[peak]) peak = i
    return peak.toFloat() / max(env.size - 1, 1)
}

/**
 * `np.convolve(env, np.ones(k)/k, mode="same")` — the boundary behaviour matters
 * (edges are zero-padded, so they are attenuated), which is exactly what makes
 * the interior peak win; a naive moving average would not match.
 */
internal fun convolveSame(a: FloatArray, k: Int): FloatArray {
    val n = a.size
    val full = FloatArray(n + k - 1)
    val w = 1.0 / k
    for (i in 0 until n) {
        val v = a[i].toDouble()
        for (j in 0 until k) full[i + j] = (full[i + j] + v * w).toFloat()
    }
    // "same" takes the centre n values of the full convolution
    val startIdx = (k - 1) / 2
    return FloatArray(n) { full[startIdx + it] }
}

// --------------------------------------------------------------------------- //
// syllable heuristics (no dictionary — good enough to anchor advice)
// --------------------------------------------------------------------------- //

/**
 * Rough English syllable split by vowel groups. Port of word_diff._syllables —
 * not linguistically exact, but gives usable anchors like ['spe','cial'].
 */
internal fun syllables(word: String): List<String> {
    val w = word.filter { it in 'a'..'z' || it in 'A'..'Z' }
    if (w.isEmpty()) return listOf(word)
    val lw = w.lowercase()
    val vowels = "aeiouy"
    val groups = ArrayList<Pair<Int, Int>>()
    var i = 0
    val n = lw.length
    while (i < n) {
        if (lw[i] in vowels) {
            var j = i
            while (j < n && lw[j] in vowels) j++
            groups.add(i to j)
            i = j
        } else i++
    }
    if (groups.size <= 1) return listOf(w)
    val cuts = arrayListOf(0)
    for (g in 0 until groups.size - 1) {
        val e0 = groups[g].second
        val s1 = groups[g + 1].first
        var mid = (e0 + s1) / 2
        mid = max(cuts.last() + 1, min(mid, n - 1))
        cuts.add(mid)
    }
    cuts.add(n)
    val parts = (0 until cuts.size - 1).map { w.substring(cuts[it], cuts[it + 1]) }
        .filter { it.isNotEmpty() }
    return if (parts.isEmpty()) listOf(w) else parts
}

/** Render a word with one syllable upper-cased: spe-CIAL. Port of _emphasize. */
internal fun emphasize(sylls: List<String>, idx: Int): String {
    val i = max(0, min(idx, sylls.size - 1))
    return sylls.mapIndexed { k, s -> if (k == i) s.uppercase() else s }.joinToString("-")
}

internal fun syllIdx(pos: Float, nsyll: Int): Int =
    max(0, min((pos * nsyll).toInt(), nsyll - 1))

internal fun normToken(tok: String): String =
    tok.lowercase().filter { it in 'a'..'z' }

// --------------------------------------------------------------------------- //
// per-word verbaliser
// --------------------------------------------------------------------------- //

/** Python's f"{x:.0%}" — percent with no decimals, round-half-EVEN (not half-up). */
private fun pct(x: Float): String = "${Math.rint(x.toDouble() * 100.0).toInt()}%"

/**
 * Port of word_diff._describe_word: (chinese_tip, tags) for one flagged word by
 * comparing the two audio spans. Empty tip if nothing specific stands out.
 */
internal fun describeWord(
    word: String,
    refSpan: FloatArray, learnerSpan: FloatArray,
    refDur: Float, learnerDur: Float,
    pitch: PitchEstimator,
): Pair<String, List<String>> {
    val parts = ArrayList<String>()
    val tags = ArrayList<String>()

    // --- stress location ---
    val rp = stressPos(refSpan)
    val lp = stressPos(learnerSpan)
    if (rp != null && lp != null && abs(rp - lp) >= STRESS_POS_DELTA) {
        val sylls = syllables(word)
        val n = sylls.size
        if (n >= 2) {
            val ri = syllIdx(rp, n)
            val li = syllIdx(lp, n)
            if (ri != li) {
                parts.add(
                    "重音位置不同：原声重读第 ${ri + 1} 个音节（${emphasize(sylls, ri)}），" +
                        "你却重读了第 ${li + 1} 个音节（${emphasize(sylls, li)}）。" +
                        "试着弱读其它音节、只把 “${sylls[ri]}” 读得更重更长。"
                )
                tags.add("stress_shift")
            }
        }
        if (tags.isEmpty()) {  // single-syllable, or the syllabifier gave one part
            val whereRef = if (rp > 0.5f) "后半部" else "前半部"
            val whereYou = if (lp > 0.5f) "后半部" else "前半部"
            parts.add("用力点不同：原声把这个词的重音放在${whereRef}，你放在了${whereYou}。")
            tags.add("stress_half")
        }
    }

    // --- linking / vowel length via duration ---
    if (refDur > 0f && learnerDur > 0f) {
        val ratio = learnerDur / refDur
        if (ratio < SHORT_RATIO) {
            parts.add(
                "你把这个词读得太短（约为原声的 ${pct(ratio)}），像是吞音了。" +
                    "原声把元音拉得更长更饱满，放慢、把元音读足。"
            )
            tags.add("clipped")
        } else if (ratio > LONG_RATIO) {
            parts.add("你把这个词拖得过长（约为原声的 ${pct(ratio)}），原声更干脆利落。")
            tags.add("dragged")
        }
    }

    // --- pitch movement ---
    val rs = pitch.slopeHz(refSpan)
    val ls = pitch.slopeHz(learnerSpan)
    if (rs != null && abs(rs) >= PITCH_MIN_SLOPE) {
        val refDir = if (rs > 0) "上扬" else "下沉"
        if (ls == null || abs(ls) < PITCH_MIN_SLOPE || (ls > 0) != (rs > 0)) {
            val youDir = when {
                ls == null || abs(ls) < PITCH_MIN_SLOPE -> "偏平"
                ls > 0 -> "上扬"
                else -> "下沉"
            }
            parts.add("音高走向不同：原声在这个词上${refDir}，你读得${youDir}。跟着原声让音调${refDir}。")
            tags.add("pitch")
        }
    }

    // keep it focused: at most two points
    return parts.take(2).joinToString(" ") to tags.take(2)
}

internal fun describeLinking(w1: String, w2: String): String =
    "连读处：原声把 “$w1” 和 “$w2” 连在一起、中间不停顿，你却分开读了。" +
        "把 “$w1” 的词尾接到 “$w2” 开头，连成一口气（$w1‿$w2）。"

// --------------------------------------------------------------------------- //
// main entry
// --------------------------------------------------------------------------- //

/**
 * Port of word_diff.diagnose_words. Compares flagged reference words against
 * their matched learner words; returns diffs keyed by (si, wi).
 *
 * `refFlat` carries clip-relative reference seconds; `learnerFlat` carries
 * learner-recording seconds.
 */
fun diagnoseWords(
    refWav: FloatArray,
    learnerWav: FloatArray,
    refFlat: List<RefWord>,
    learnerFlat: List<LearnerWord>,
    pitch: PitchEstimator = NoPitch,
): Map<Pair<Int, Int>, WordDiff> {
    val out = LinkedHashMap<Pair<Int, Int>, WordDiff>()
    if (refFlat.isEmpty() || learnerFlat.isEmpty()) return out

    val refTokens = refFlat.map { normToken(it.word) }
    val learnerTokens = learnerFlat.map { normToken(it.word) }
    val refToLearner = matchingIndices(refTokens, learnerTokens)

    for ((ri, r) in refFlat.withIndex()) {
        val li = refToLearner[ri]

        // word-level pronunciation delta (only for flagged, matched words)
        if ((r.status == "weak" || r.status == "bad") && li != null) {
            val lw = learnerFlat[li]
            val refSpan = slice(refWav, r.start, r.end)
            val learnerSpan = slice(learnerWav, lw.start, lw.end)
            if (refSpan.isNotEmpty() && learnerSpan.isNotEmpty()) {
                val (tip, tags) = describeWord(
                    r.word, refSpan, learnerSpan, r.end - r.start, lw.end - lw.start, pitch,
                )
                if (tip.isNotEmpty()) {
                    out[r.si to r.wi] = WordDiff(
                        si = r.si, wi = r.wi, word = r.word, tip = tip,
                        learnerStart = round3(lw.start), learnerEnd = round3(lw.end),
                        tags = tags.toMutableList(),
                    )
                }
            }
        }

        // linking at the junction to the next word in the SAME sentence
        if (ri + 1 < refFlat.size && refFlat[ri + 1].si == r.si) {
            val nxt = refFlat[ri + 1]
            val refGap = nxt.start - r.end
            val lj = refToLearner[ri + 1]
            if (li != null && lj != null && refGap <= LINK_REF_MAX_GAP) {
                val learnerGap = learnerFlat[lj].start - learnerFlat[li].end
                if (learnerGap - refGap >= LINK_EXTRA_GAP) {
                    val key = r.si to r.wi
                    val linkTip = describeLinking(r.word, nxt.word)
                    val existing = out[key]
                    if (existing != null) {
                        existing.tip = (existing.tip + " " + linkTip).trim()
                        existing.tags.add("link")
                    } else {
                        out[key] = WordDiff(
                            si = r.si, wi = r.wi, word = r.word, tip = linkTip,
                            learnerStart = round3(learnerFlat[li].start),
                            learnerEnd = round3(learnerFlat[lj].end),
                            tags = mutableListOf("link"),
                        )
                    }
                }
            }
        }
    }
    return out
}

/**
 * Equivalent of Python's `difflib.SequenceMatcher(autojunk=False).get_matching_blocks()`
 * reduced to what diagnose_words uses: a refIdx -> learnerIdx map over the
 * matching blocks.
 *
 * difflib's matching blocks come from recursively taking the LONGEST matching
 * block (leftmost-longest, tie-broken toward the earliest i then earliest j)
 * and recursing on the segments either side, which is NOT the same as an LCS —
 * it can yield fewer matched pairs. This reproduces that algorithm rather than
 * approximating it, so the word pairing matches macOS exactly.
 */
internal fun matchingIndices(a: List<String>, b: List<String>): Map<Int, Int> {
    val out = HashMap<Int, Int>()
    // b2j: value -> positions in b (difflib's index; autojunk disabled, and we
    // have no "popular" pruning since word lists are short)
    val b2j = HashMap<String, MutableList<Int>>()
    for ((j, v) in b.withIndex()) b2j.getOrPut(v) { ArrayList() }.add(j)

    fun findLongestMatch(alo: Int, ahi: Int, blo: Int, bhi: Int): Triple<Int, Int, Int> {
        var besti = alo; var bestj = blo; var bestsize = 0
        var j2len = HashMap<Int, Int>()
        for (i in alo until ahi) {
            val newj2len = HashMap<Int, Int>()
            for (j in b2j[a[i]] ?: emptyList<Int>()) {
                if (j < blo) continue
                if (j >= bhi) break
                val k = (j2len[j - 1] ?: 0) + 1
                newj2len[j] = k
                if (k > bestsize) { besti = i - k + 1; bestj = j - k + 1; bestsize = k }
            }
            j2len = newj2len
        }
        return Triple(besti, bestj, bestsize)
    }

    // difflib's iterative queue over (alo, ahi, blo, bhi)
    val queue = ArrayDeque<IntArray>()
    queue.add(intArrayOf(0, a.size, 0, b.size))
    while (queue.isNotEmpty()) {
        val (alo, ahi, blo, bhi) = queue.removeLast().let {
            listOf(it[0], it[1], it[2], it[3])
        }
        val (i, j, k) = findLongestMatch(alo, ahi, blo, bhi)
        if (k > 0) {
            for (t in 0 until k) out[i + t] = j + t
            if (alo < i && blo < j) queue.add(intArrayOf(alo, i, blo, j))
            if (i + k < ahi && j + k < bhi) queue.add(intArrayOf(i + k, ahi, j + k, bhi))
        }
    }
    return out
}

private fun round3(x: Float): Float = round(x * 1000f) / 1000f
