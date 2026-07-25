package com.nativelingo.scoring

import com.nativelingo.scoring.segment.Sentence
import com.nativelingo.scoring.segment.SentenceSegmenter
import com.nativelingo.scoring.segment.TimedWord
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * `transcribe.py` sentence-building parity (FR-2 / FR-M3).
 *
 * Everything here is asserted **exactly** — sentence text, index, boundaries and
 * every word. The values are integers, strings and 3-dp times produced by
 * deterministic Python, so a tolerance would only hide a systematic error, and a
 * one-sentence drift in segmentation shifts every clip and every score after it.
 *
 * Fixtures: `golden/seg/` (see `scripts/capture_golden.py:dump_segmentation`).
 */
class SegmentationParityTest {

    private fun golden(name: String) =
        javaClass.getResourceAsStream("/golden/seg/$name")
            ?: error("missing golden resource: /golden/seg/$name")

    private fun text(name: String) = golden(name).reader().readText()

    private val g by lazy { TestJson.obj(text("segmentation.json")) }

    @Suppress("UNCHECKED_CAST")
    private fun words(raw: Any?): List<TimedWord> =
        (raw as List<Any?>).map {
            val m = it as Map<String, Any?>
            TimedWord(m.str("word"), (m["start"] as Number).toDouble(), (m["end"] as Number).toDouble())
        }

    @Suppress("UNCHECKED_CAST")
    private fun sentences(raw: Any?): List<Sentence> =
        (raw as List<Any?>).map {
            val m = it as Map<String, Any?>
            Sentence(
                index = m.int("index"),
                start = (m["start"] as Number).toDouble(),
                end = (m["end"] as Number).toDouble(),
                text = m.str("text"),
                words = words(m["words"]),
            )
        }

    private fun assertSame(expected: List<Sentence>, actual: List<Sentence>, label: String) {
        assertEquals(expected.size, actual.size, "$label: sentence count")
        for (i in expected.indices) {
            val e = expected[i]
            val a = actual[i]
            assertEquals(e.index, a.index, "$label[$i]: index")
            assertEquals(e.text, a.text, "$label[$i]: text")
            assertEquals(e.start, a.start, "$label[$i]: start")
            assertEquals(e.end, a.end, "$label[$i]: end")
            assertEquals(e.words.size, a.words.size, "$label[$i]: word count")
            for (j in e.words.indices) {
                assertEquals(e.words[j], a.words[j], "$label[$i].words[$j]")
            }
        }
    }

    @Test
    fun the_real_cached_transcript_merges_into_the_same_sentences() {
        // The load-bearing case: 1944 whisper words from a real 10-minute news
        // clip, with the tokens whisper actually produces ("long -considered",
        // leading-dash words, quoted clause ends). Synthetic text would not have
        // found the tie-break or the give-up branch.
        val input = words(TestJson.parse(text("reference_words.json")))
        val expected = sentences(TestJson.parse(text("reference_sentences.json")))
        val meta = g["reference"] as Map<String, Any?>
        assertEquals(meta.int("n_words"), input.size, "fixture word count")
        assertEquals(meta.int("n_sentences"), expected.size, "fixture sentence count")

        assertSame(expected, SentenceSegmenter.mergeIntoSentences(input), "reference")
    }

    @Test
    fun the_reference_corpus_exercises_both_split_outcomes() {
        // Guards the fixture rather than the port. If the corpus ever stopped
        // containing over-long sentences, the case above would still pass while
        // testing none of FR-M3. Sub-split chunks are recognisable: only a
        // terminal-punctuation word can end a *merged* sentence.
        val expected = sentences(TestJson.parse(text("reference_sentences.json")))
        val subSplit = expected.count { !SentenceSegmenter.endsSentence(it.words.last().word) }
        assertTrue(subSplit >= 40, "expected plenty of FR-M3 sub-splits, got $subSplit")

        val gaveUp = expected.count { it.words.size > SentenceSegmenter.SPLIT_WORDS }
        assertTrue(gaveUp >= 1, "expected at least one over-long sentence left whole, got $gaveUp")
    }

    @Test
    fun synthetic_cases_match_python() {
        val cases = g.objList("cases")
        assertTrue(cases.size >= 15, "expected the full case list, got ${cases.size}")
        for (c in cases) {
            val name = c.str("name")
            val subSplit = c["subsplit"] as Boolean
            val got = SentenceSegmenter.mergeIntoSentences(words(c["words"]), subSplit)
            assertSame(sentences(c["expect"]), got, "$name (${c.str("note")})")
        }
    }

    @Test
    fun the_learner_path_does_not_sub_split() {
        // The asymmetry is the point: the same over-long word list yields one
        // sentence for the learner and several for the reference. Asserted both
        // ways so a future "unify the two paths" refactor fails here.
        val c = g.objList("cases").first { it.str("name") == "learner_long_not_split" }
        val w = words(c["words"])
        assertTrue(SentenceSegmenter.needsSplit(w), "the fixture must be over the limits")
        assertEquals(1, SentenceSegmenter.mergeIntoSentences(w, subSplit = false).size,
            "learner recordings keep the sentence they were recorded against")
        assertTrue(SentenceSegmenter.mergeIntoSentences(w, subSplit = true).size > 1,
            "reference material gets sub-split")
    }

    @Test
    fun split_points_match_python_including_the_tie_break() {
        for (c in g.objList("split_points")) {
            val expected = (c["expect"] as Number?)?.toInt()
            val got = SentenceSegmenter.bestSplitPoint(words(c["words"]))
            assertEquals(expected, got, c.str("name"))
        }
    }

    @Test
    fun a_wordless_segment_keeps_its_text() {
        // faster-whisper can return a segment with no word timestamps; macOS
        // falls back to a whole-segment pseudo-word so the text is not lost.
        // On Android that assembly belongs to :core-asr, so this test pins the
        // composition it has to perform.
        @Suppress("UNCHECKED_CAST")
        val fb = g["segment_fallback"] as Map<String, Any?>
        val built = ArrayList<TimedWord>()
        for (seg in fb.objList("segments")) {
            val segWords = seg["words"]
            if (segWords == null) {
                val token = SentenceSegmenter.normalizeToken(seg.str("text"))
                if (token != null) {
                    built.add(TimedWord(token, (seg["start"] as Number).toDouble(),
                        (seg["end"] as Number).toDouble()))
                }
            } else {
                for (w in words(segWords)) {
                    SentenceSegmenter.normalizeToken(w.word)?.let {
                        built.add(TimedWord(it, w.start, w.end))
                    }
                }
            }
        }
        assertSame(sentences(fb["expect"]), SentenceSegmenter.mergeIntoSentences(built, false),
            "segment fallback")
    }

    @Test
    fun round3_is_half_even_on_the_exact_binary_value() {
        for (c in g.objList("round3")) {
            val x = (c["in"] as Number).toDouble()
            val expected = (c["out"] as Number).toDouble()
            assertEquals(expected, SentenceSegmenter.round3(x), "round3($x)")
        }
        // The two idioms this replaces, spelled out so the reason survives:
        // both are half-UP and disagree with Python on an exact tie.
        assertEquals(0.062, SentenceSegmenter.round3(0.0625), "0.0625 rounds DOWN to even")
        assertEquals(0.063, Math.round(0.0625 * 1000) / 1000.0, "Math.round is half-up")
        assertEquals("0.063", String.format(java.util.Locale.ROOT, "%.3f", 0.0625),
            "%.3f is half-up")

        // A failed alignment can hand us these; Python returns them unchanged
        // and BigDecimal would throw.
        assertTrue(SentenceSegmenter.round3(Double.NaN).isNaN())
        assertEquals(Double.POSITIVE_INFINITY, SentenceSegmenter.round3(Double.POSITIVE_INFINITY))
        assertEquals(Double.NEGATIVE_INFINITY, SentenceSegmenter.round3(Double.NEGATIVE_INFINITY))
    }

    @Test
    fun the_token_predicates_match_python() {
        for (c in g.objList("regexes")) {
            val t = c.str("token")
            val label = "token ${t.map { it.code }}"   // control chars are the interesting ones
            assertEquals(c["sentence_end"] as Boolean, SentenceSegmenter.endsSentence(t),
                "$label: sentence end")
            assertEquals(c["clause_end"] as Boolean, SentenceSegmenter.endsClause(t),
                "$label: clause end")
            assertEquals(c.str("conj_key"), SentenceSegmenter.conjunctionKey(t), "$label: conj key")
            assertEquals(c["is_conj"] as Boolean,
                SentenceSegmenter.conjunctionKey(t) in SentenceSegmenter.CONJUNCTIONS,
                "$label: is conjunction")
            assertEquals(c.str("py_strip"), SentenceSegmenter.pyStrip(t), "$label: strip")
        }
        // and state what the probes are guarding, so a regex "tidy-up" that drops
        // (?d) fails with the reason attached
        assertTrue(SentenceSegmenter.endsSentence("ok.\n"), "Python's \$ allows a trailing newline")
        assertFalse(SentenceSegmenter.endsSentence("ok.\r"), "...but only a newline")
        assertFalse(SentenceSegmenter.endsSentence("ok.\u2028"), "...not a line separator")
        assertFalse(SentenceSegmenter.endsSentence("ok.}"), "} is not in the closer class")
        assertNull(SentenceSegmenter.normalizeToken(" \u00a0\t"), "an all-space token is dropped")
    }

    @Test
    fun the_python_whitespace_class_is_reproduced_over_the_whole_bmp() {
        // Java offers three overlapping notions and none of them is Python's:
        // isWhitespace() excludes the no-break spaces, isSpaceChar() excludes
        // tab and newline, and neither knows NEL. Rather than trust the union,
        // check it against the code points Python actually accepts.
        @Suppress("UNCHECKED_CAST")
        val expected = (g["pyspace"] as List<Any?>).map { (it as Number).toInt() }.toSet()
        assertTrue(expected.size >= 25, "fixture looks truncated: ${expected.size} code points")
        val mine = (0..0xFFFF).filter { SentenceSegmenter.isPySpace(it.toChar()) }.toSet()
        assertEquals(emptySet(), expected - mine, "code points Python calls space and we do not")
        assertEquals(emptySet(), mine - expected, "code points we call space and Python does not")
    }
}
