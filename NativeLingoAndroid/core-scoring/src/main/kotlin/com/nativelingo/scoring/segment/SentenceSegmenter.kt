package com.nativelingo.scoring.segment

import java.math.BigDecimal
import java.math.RoundingMode
import kotlin.math.abs

/** One transcribed word with its timing, in seconds. Mirrors `{word, start, end}`. */
data class TimedWord(val word: String, val start: Double, val end: Double)

/**
 * A shadowable unit: what the learner picks from the video and records against.
 * Mirrors `transcribe.py`'s sentence dict `{index, start, end, text, words}`.
 */
data class Sentence(
    val index: Int,
    val start: Double,
    val end: Double,
    val text: String,
    val words: List<TimedWord>,
)

/**
 * Port of the sentence-building half of `backend/core/transcribe.py` (FR-2, FR-M3).
 *
 * Like [com.nativelingo.scoring.audio.AudioPreproc], this sits in `:core-scoring`
 * rather than `:core-asr` even though its input comes from Whisper: sentence
 * boundaries decide which reference span is clipped and scored, so they are part
 * of the score contract and must be testable on the JVM with no model present.
 * `:core-asr` keeps only the sherpa-onnx recognition itself, and hands its words
 * here.
 *
 * Two entry points in Python, one function here:
 *
 *  * the **reference** path (`_merge_words_into_sentences`) merges by terminal
 *    punctuation and then sub-splits over-long sentences — [mergeIntoSentences]
 *    with `subSplit = true`;
 *  * the **learner** path (`_merge_into_sentences`, used by `transcribe_waveform`)
 *    merges by punctuation only — `subSplit = false`. The asymmetry is
 *    deliberate: FR-M3's job is to give the learner shadowable reference chunks,
 *    and re-splitting their own recording by *its* clause structure would break
 *    the 1:1 correspondence with the chunk they chose.
 *
 * Both Python paths round word times to 3 dp before merging (`_aligned_words` for
 * the reference, the dict construction for the learner), so this function rounds
 * on the way in — that is the composition, not an extra step, and it keeps
 * [needsSplit]'s 8-second comparison on exactly the values macOS uses. Note the
 * consequence: `_merge_words_into_sentences` called in isolation with raw times
 * would keep them verbatim in its output words, where this rounds them. The
 * pipeline never does that, and the golden cases are built the way the pipeline
 * builds them.
 *
 * Token cleanup (`w.word.strip()`, dropping empties, and the segment-text
 * fallback) belongs to the caller in Python too; [normalizeToken] is exposed for
 * `:core-asr` to use so both sides share one tested implementation.
 *
 * Golden fixtures: `golden/seg/` — chiefly a real 1944-word cached transcript and
 * its 164 sentences, which the merge must reproduce exactly.
 */
object SentenceSegmenter {

    /** Sentences longer than this get a second-level split (FR-M3). */
    const val SPLIT_DUR_S = 8.0

    /** ...or with more words than this. */
    const val SPLIT_WORDS = 20

    /** Never emit a fragment shorter than this. */
    const val MIN_CHUNK_WORDS = 4

    /**
     * `[.!?]['")\]]?$` and `[,;:]['")\]]?$`.
     *
     * `(?d)` (UNIX_LINES) is load-bearing, not decoration. Java's `$` matches
     * before a trailing `\r`, `\u0085`, `\u2028` or `\u2029` as well as `\n`;
     * Python's matches only before a trailing `\n`. Without the flag a token
     * ending `".\u2028"` would end a sentence on Android and not on macOS.
     */
    private val SENTENCE_END = Regex("(?d)[.!?]['\")\\]]?$")
    private val CLAUSE_END = Regex("(?d)[,;:]['\")\\]]?$")

    /** `transcribe._CONJ` — the fallback split boundary when there is no clause punctuation. */
    val CONJUNCTIONS: Set<String> = setOf(
        "and", "but", "so", "because", "which", "that", "when", "while", "if",
        "who", "whom", "whose", "where", "although", "though", "as", "since",
        "unless", "until", "after", "before",
    )

    /**
     * Python `round(x, 3)`: round-half-**even** on the exact binary value of [x].
     *
     * Both obvious Kotlin idioms are half-up and wrong on exact ties — `round`
     * and `"%.3f"` both turn 0.0625 into 0.063 where Python gives 0.062. Going
     * through [BigDecimal] also avoids the double rounding that `x * 1000` then
     * scale-back would introduce. Non-finite values pass through, as they do in
     * Python: `BigDecimal` would throw on them, and a NaN word time is
     * reachable from a failed alignment.
     */
    fun round3(x: Double): Double {
        if (!x.isFinite() || x == 0.0) return x   // preserves -0.0, like Python
        return BigDecimal(x).setScale(3, RoundingMode.HALF_EVEN).toDouble()
    }

    /**
     * True for exactly the code points Python's `str.isspace()` accepts.
     *
     * Java splits the notion three ways and none of them matches: NBSP and its
     * relatives are `isSpaceChar` but deliberately *not* `isWhitespace`, and NEL
     * (`\u0085`) is neither. Whisper is unlikely to emit any of them, but if it
     * does the divergence is silent — a stray NBSP would survive into the
     * sentence text on Android and be collapsed on macOS.
     */
    fun isPySpace(c: Char): Boolean =
        c.isWhitespace() || Character.isSpaceChar(c) || c == '\u0085'

    /** Python `str.strip()` (whitespace form). */
    fun pyStrip(s: String): String {
        var a = 0
        var b = s.length
        while (a < b && isPySpace(s[a])) a++
        while (b > a && isPySpace(s[b - 1])) b--
        return s.substring(a, b)
    }

    /**
     * `w.word.strip()` with the empty-token drop: returns null for a token that
     * is nothing but whitespace, which the Python loops `continue` past.
     */
    fun normalizeToken(raw: String): String? = pyStrip(raw).ifEmpty { null }

    /** `re.sub(r"\s+", " ", text).strip()` — Python's whitespace class, not Java's. */
    fun collapseWhitespace(text: String): String {
        val sb = StringBuilder(text.length)
        var pendingSpace = false
        for (c in text) {
            if (isPySpace(c)) {
                pendingSpace = true
            } else {
                if (pendingSpace && sb.isNotEmpty()) sb.append(' ')
                pendingSpace = false
                sb.append(c)
            }
        }
        return sb.toString()
    }

    /** `_SENTENCE_END.search(token)` — does this word close a sentence? */
    fun endsSentence(token: String): Boolean = SENTENCE_END.containsMatchIn(token)

    /** `_CLAUSE_END.search(token)` — does this word close a clause? */
    fun endsClause(token: String): Boolean = CLAUSE_END.containsMatchIn(token)

    /**
     * `re.sub(r"^[^a-zA-Z]+", "", word).lower()` — the key a word is looked up by
     * in [CONJUNCTIONS], so "-And" and "—but" match. The character class is
     * ASCII-only in Python, so it is ASCII-only here.
     */
    fun conjunctionKey(word: String): String =
        word.dropWhile { it !in 'a'..'z' && it !in 'A'..'Z' }.lowercase()

    /** `_needs_split`: too long in seconds, or in words. */
    fun needsSplit(words: List<TimedWord>): Boolean {
        if (words.isEmpty()) return false
        val dur = words.last().end - words.first().start
        return dur > SPLIT_DUR_S || words.size > SPLIT_WORDS
    }

    /**
     * `_best_split_point`: index of the first word of the right-hand chunk, or
     * null when no acceptable boundary exists (in which case the over-long
     * sentence is emitted whole — FR-M3 is deliberately conservative).
     *
     * Clause punctuation outranks a conjunction; within a rank the candidate
     * nearest the midpoint wins. Python compares `(rank, |i - mid|)` tuples with
     * a strict `<` while scanning ascending, so an exact tie goes to the *lower*
     * index — real transcripts hit that (4 times in the golden corpus), so the
     * scan order and the strict comparison both matter.
     */
    fun bestSplitPoint(words: List<TimedWord>): Int? {
        val n = words.size
        if (n < 2 * MIN_CHUNK_WORDS) return null
        val mid = n / 2.0
        var best: Int? = null
        var bestRank = 0
        var bestDist = 0.0
        for (i in MIN_CHUNK_WORDS..(n - MIN_CHUNK_WORDS)) {
            val rank = when {
                endsClause(words[i - 1].word) -> 0
                conjunctionKey(words[i].word) in CONJUNCTIONS -> 1
                else -> continue
            }
            val dist = abs(i - mid)
            if (best == null || rank < bestRank || (rank == bestRank && dist < bestDist)) {
                best = i
                bestRank = rank
                bestDist = dist
            }
        }
        return best
    }

    /** `_split_long`: recursive, because a half can still be over the limits. */
    private fun splitLong(words: List<TimedWord>, out: MutableList<List<TimedWord>>) {
        if (!needsSplit(words)) {
            out.add(words)
            return
        }
        val cut = bestSplitPoint(words)
        if (cut == null) {
            out.add(words)
            return
        }
        splitLong(words.subList(0, cut), out)
        splitLong(words.subList(cut, words.size), out)
    }

    /**
     * Merge an ordered word list into sentences.
     *
     * @param words whisper's words, in order, with the tokens already cleaned by
     *   [normalizeToken] (that is where Python does it too).
     * @param subSplit apply FR-M3's clause-level sub-split. True for reference
     *   material, false for the learner's own recording.
     */
    fun mergeIntoSentences(words: List<TimedWord>, subSplit: Boolean = true): List<Sentence> {
        val rounded = words.map { TimedWord(it.word, round3(it.start), round3(it.end)) }
        val sentences = ArrayList<Sentence>()

        fun emit(chunk: List<TimedWord>) {
            val text = collapseWhitespace(chunk.joinToString(" ") { it.word })
            if (text.isEmpty()) return
            sentences.add(
                Sentence(
                    index = sentences.size,
                    start = round3(chunk.first().start),
                    end = round3(chunk.last().end),
                    text = text,
                    words = chunk.toList(),
                )
            )
        }

        val cur = ArrayList<TimedWord>()
        fun flush() {
            if (cur.isNotEmpty()) {
                if (subSplit) {
                    val chunks = ArrayList<List<TimedWord>>()
                    splitLong(cur.toList(), chunks)
                    chunks.forEach(::emit)
                } else {
                    emit(cur.toList())
                }
            }
            cur.clear()
        }

        for (w in rounded) {
            cur.add(w)
            if (endsSentence(w.word)) flush()
        }
        flush()
        return sentences
    }
}
