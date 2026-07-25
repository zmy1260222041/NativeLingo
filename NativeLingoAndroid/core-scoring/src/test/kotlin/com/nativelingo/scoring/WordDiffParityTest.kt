package com.nativelingo.scoring

import com.nativelingo.scoring.io.NpyReader
import com.nativelingo.scoring.io.toFloatArray1d
import com.nativelingo.scoring.worddiff.LearnerWord
import com.nativelingo.scoring.worddiff.NoPitch
import com.nativelingo.scoring.worddiff.RefWord
import com.nativelingo.scoring.worddiff.diagnoseWords
import com.nativelingo.scoring.worddiff.matchingIndices
import com.nativelingo.scoring.worddiff.rmsEnvelope
import com.nativelingo.scoring.worddiff.slice
import com.nativelingo.scoring.worddiff.stressPos
import com.nativelingo.scoring.worddiff.syllables
import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * FR-7 parity: the per-word improvement directions (读法改进方向).
 *
 * Three levels, cheapest-to-break first:
 *  1. primitives — RMS-envelope length, stress position, syllable split, per
 *     word, element-wise against macOS. This is where an off-by-one in the
 *     framing or the np.convolve("same") boundary would show up.
 *  2. tips — the full diagnosis with pitch DISABLED, asserted exactly (tags,
 *     word set, and the Chinese tip strings) against the macOS `_nopitch`
 *     golden. Praat's pitch tracker has no bit-exact JVM equivalent, so pitch
 *     tips are excluded here by construction (see docs/android-migration.md §4).
 *  3. difflib equivalence — the ref<->learner word pairing.
 */
class WordDiffParityTest {

    private val cases = listOf("slow", "crossvoice")

    private fun golden(path: String) =
        javaClass.getResourceAsStream("/golden/$path")
            ?: error("missing golden resource: /golden/$path")

    private fun json(path: String) =
        TestJson.obj(golden(path).bufferedReader().use { it.readText() })

    private fun wav(name: String) = NpyReader.read(golden("wav/$name.npy")).toFloatArray1d()

    private fun learnerKey(case: String) =
        if (case == "slow") "slow_samantha" else "crossvoice_daniel"

    private fun refWords(case: String): List<RefWord> =
        json("worddiff/${case}_inputs.json").objList("ref").map {
            RefWord(it.int("si"), it.int("wi"), it.str("word"),
                it.f("start"), it.f("end"), it.str("status"))
        }

    private fun learnerWords(case: String): List<LearnerWord> =
        json("worddiff/${case}_inputs.json").objList("learner").map {
            LearnerWord(it.str("word"), it.f("start"), it.f("end"))
        }

    @Test
    fun acoustic_primitives_match_macos() {
        for (case in cases) {
            val refWav = wav("ref_samantha")
            val lrnWav = wav(learnerKey(case))
            val prims = json("worddiff/${case}_inputs.json").objList("primitives")
            assertTrue(prims.isNotEmpty(), "$case: no primitives in golden")

            for (p in prims) {
                val word = p.str("word")
                val rs = slice(refWav, p.f("ref_start"), p.f("ref_end"))
                val ls = slice(lrnWav, p.f("learner_start"), p.f("learner_end"))

                // envelope framing must agree exactly — an off-by-one here
                // silently shifts every stress position downstream.
                assertEquals(p.int("ref_env_len"), rmsEnvelope(rs)?.size ?: 0,
                    "$case/$word: ref envelope length")
                assertEquals(p.int("learner_env_len"), rmsEnvelope(ls)?.size ?: 0,
                    "$case/$word: learner envelope length")

                assertStressPos(p.fOrNull("ref_stress_pos"), stressPos(rs), "$case/$word ref")
                assertStressPos(p.fOrNull("learner_stress_pos"), stressPos(ls), "$case/$word learner")

                assertEquals(p.strList("syllables"), syllables(word), "$case/$word: syllable split")
            }
        }
    }

    private fun assertStressPos(expected: Float?, actual: Float?, what: String) {
        if (expected == null) {
            assertTrue(actual == null, "$what: expected no stress position, got $actual")
            return
        }
        assertTrue(actual != null, "$what: expected stress position $expected, got null")
        // the position is peak_index / (len-1) — a discrete grid, so the only way
        // to be "close but wrong" is to pick a different frame; 1e-6 catches that.
        assertTrue(abs(expected - actual!!) < 1e-6f,
            "$what: stress position $actual != macOS $expected")
    }

    @Test
    fun pitch_free_tips_match_macos_exactly() {
        for (case in cases) {
            val refWav = wav("ref_samantha")
            val lrnWav = wav(learnerKey(case))
            val goldenDiffs = json("worddiff/${case}_tips_nopitch.json").objList("diffs")

            val result = diagnoseWords(refWav, lrnWav, refWords(case), learnerWords(case), NoPitch)
            val got = result.values.sortedWith(compareBy({ it.si }, { it.wi }))

            assertEquals(goldenDiffs.size, got.size,
                "$case: diagnosed word count — macOS ${goldenDiffs.map { it.str("word") }}, " +
                    "kotlin ${got.map { it.word }}")
            for ((i, g) in goldenDiffs.withIndex()) {
                val k = got[i]
                assertEquals(g.int("wi"), k.wi, "$case: word index at slot $i")
                assertEquals(g.str("word"), k.word, "$case: word at slot $i")
                assertEquals(g.strList("tags"), k.tags.toList(), "$case/${k.word}: tags")
                assertEquals(g.str("tip"), k.tip, "$case/${k.word}: tip text")
                assertTrue(abs(g.f("learner_start") - k.learnerStart) < 1e-4f,
                    "$case/${k.word}: learner_start")
                assertTrue(abs(g.f("learner_end") - k.learnerEnd) < 1e-4f,
                    "$case/${k.word}: learner_end")
            }
        }
    }

    @Test
    fun difflib_matching_blocks_equivalent() {
        // identical sequences -> identity map
        val a = listOf("the", "quick", "brown", "fox")
        assertEquals(mapOf(0 to 0, 1 to 1, 2 to 2, 3 to 3), matchingIndices(a, a))

        // a dropped learner word shifts the tail
        assertEquals(
            mapOf(0 to 0, 2 to 1, 3 to 2),
            matchingIndices(a, listOf("the", "brown", "fox")),
        )

        // an inserted learner word
        assertEquals(
            mapOf(0 to 0, 1 to 1, 2 to 3, 3 to 4),
            matchingIndices(a, listOf("the", "quick", "um", "brown", "fox")),
        )

        // no overlap at all
        assertEquals(emptyMap(), matchingIndices(a, listOf("cat", "sleeps")))

        // a repeated token
        assertEquals(
            mapOf(0 to 0, 1 to 1, 2 to 2),
            matchingIndices(listOf("the", "the", "cat"), listOf("the", "the", "cat")),
        )
    }
}
