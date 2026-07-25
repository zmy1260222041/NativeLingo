package com.nativelingo.scoring

import com.nativelingo.scoring.detail.SentenceSpan
import com.nativelingo.scoring.detail.WordSpan
import com.nativelingo.scoring.detail.computeSentenceDetails
import com.nativelingo.scoring.io.NpyReader
import com.nativelingo.scoring.io.frames2dInt
import com.nativelingo.scoring.io.toFloatArray1d
import com.nativelingo.scoring.score.CalibrationLoader
import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * FR-6 (sentence level) parity: the sentence's accuracy, its duration-ratio
 * fluency, and the learner replay span — which is what FR-8's A/B playback
 * seeks to, so an error here sends the learner to the wrong audio.
 *
 * The golden is captured with a NON-ZERO learner_offset so the trim-offset
 * shift is actually exercised (a zero offset would hide an unapplied offset).
 */
class SentenceDetailParityTest {

    private val calib by lazy { CalibrationLoader.loadDefault() }
    private val pairs = listOf("samevoice", "speakervariance", "wrongtext", "slow")

    private fun golden(path: String) =
        javaClass.getResourceAsStream("/golden/$path")
            ?: error("missing golden resource: /golden/$path")

    private fun json(path: String) =
        TestJson.obj(golden(path).bufferedReader().use { it.readText() })

    private fun words(name: String): List<WordSpan> =
        json("pair/${name}_detail.json").objList("words").map {
            WordSpan(it.str("word"), it.f("start"), it.f("end"))
        }

    @Test
    fun sentence_details_match_macos() {
        for (name in pairs) {
            val path = NpyReader.read(golden("pair/${name}_path.npy")).frames2dInt()
            val costs = NpyReader.read(golden("pair/${name}_costs.npy")).toFloatArray1d()
            val sentJson = json("pair/${name}_sentence.json")
            val offset = sentJson.f("learner_offset")
            val g = sentJson.objList("sentences").single()
            val w = words(name)
            assertTrue(w.isNotEmpty(), "$name: no words in detail golden")

            val got = computeSentenceDetails(
                path, costs,
                listOf(SentenceSpan(g.str("text"), g.f("start"), g.f("end"), w)),
                calib, offset,
            )
            assertEquals(1, got.size, "$name: sentence count")
            val s = got[0]

            assertEquals(0, s.index, "$name: index")
            assertTrue(abs(g.f("accuracy") - s.accuracy) <= 2.0f,
                "$name: sentence accuracy ${s.accuracy} vs macOS ${g.f("accuracy")}")
            assertTrue(abs(g.f("fluency") - s.fluency) <= 3.0f,
                "$name: sentence fluency ${s.fluency} vs macOS ${g.f("fluency")}")
            // replay spans drive FR-8 A/B playback — 20ms (one frame) is the bar
            assertTrue(abs(g.f("learner_start") - s.learnerStart) <= 0.02f,
                "$name: learner_start ${s.learnerStart} vs macOS ${g.f("learner_start")}")
            assertTrue(abs(g.f("learner_end") - s.learnerEnd) <= 0.02f,
                "$name: learner_end ${s.learnerEnd} vs macOS ${g.f("learner_end")}")
            // the nested per-word projection must still hold
            assertEquals(w.size, s.words.size, "$name: word count")
        }
    }

    @Test
    fun learner_offset_shifts_replay_span() {
        // guards the offset actually being applied — an unapplied offset would
        // still pass the golden test if the golden had been captured at 0.
        val path = NpyReader.read(golden("pair/slow_path.npy")).frames2dInt()
        val costs = NpyReader.read(golden("pair/slow_costs.npy")).toFloatArray1d()
        val sentence = SentenceSpan("x", 0.02f, 2.46f, listOf(WordSpan("x", 0.02f, 2.46f)))

        val a = computeSentenceDetails(path, costs, listOf(sentence), calib, 0f)[0]
        val b = computeSentenceDetails(path, costs, listOf(sentence), calib, 0.5f)[0]
        assertTrue(abs((b.learnerStart - a.learnerStart) - 0.5f) < 1e-3f,
            "offset not applied to learner_start")
        assertTrue(abs((b.learnerEnd - a.learnerEnd) - 0.5f) < 1e-3f,
            "offset not applied to learner_end")
        assertEquals(a.accuracy, b.accuracy, "offset must not change scoring")
    }
}
