package com.nativelingo.scoring

import com.nativelingo.scoring.feedback.ProsodySummary
import com.nativelingo.scoring.feedback.generateFeedback
import com.nativelingo.scoring.io.NpyReader
import com.nativelingo.scoring.io.frames2dInt
import com.nativelingo.scoring.io.toFloatArray1d
import com.nativelingo.scoring.score.CalibrationLoader
import com.nativelingo.scoring.score.TrackBResult
import com.nativelingo.scoring.score.findProblemRegions
import com.nativelingo.scoring.score.scoreTrackB
import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * FR-4 (problem regions) + FR-9 (feedback rule engine) parity.
 *
 * Both are deterministic functions of the DTW result, so unlike the scores
 * these are asserted EXACTLY: a region boundary or a tip string that differs
 * from macOS is a port bug, not float drift. The learner reads the tips
 * verbatim, so "close enough" is not a meaningful bar here.
 */
class FeedbackParityTest {

    private val calib by lazy { CalibrationLoader.loadDefault() }
    private val pairs = listOf("samevoice", "speakervariance", "wrongtext", "slow")

    private fun golden(path: String) =
        javaClass.getResourceAsStream("/golden/$path")
            ?: error("missing golden resource: /golden/$path")

    private fun json(path: String) =
        TestJson.obj(golden(path).bufferedReader().use { it.readText() })

    private class Case(
        val trackB: TrackBResult,
        val golden: Map<String, Any?>,
        val path: Array<IntArray>,
        val costs: FloatArray,
    )

    private fun case(name: String): Case {
        val path = NpyReader.read(golden("pair/${name}_path.npy")).frames2dInt()
        val costs = NpyReader.read(golden("pair/${name}_costs.npy")).toFloatArray1d()
        val flu = json("pair/${name}_fluency.json")
        val g = json("pair/${name}_problems.json")
        val tb = scoreTrackB(
            path, costs, g.f("raw_path_cost"),
            flu.int("ref_len"), flu.int("learner_len"),
            flu.f("pause_per_s"), flu.f("pause_ratio"), calib,
        )
        return Case(tb, g, path, costs)
    }

    @Test
    fun problem_regions_match_macos() {
        for (name in pairs) {
            val c = case(name)
            val goldenRegions = c.golden.objList("problems")

            // via scoreTrackB and directly — both entry points must agree
            assertEquals(c.trackB.problems, findProblemRegions(c.path, c.costs, calib),
                "$name: scoreTrackB vs findProblemRegions disagree")

            assertEquals(goldenRegions.size, c.trackB.problems.size,
                "$name: region count (macOS ${goldenRegions.size}, kotlin ${c.trackB.problems.size})")
            for ((i, g) in goldenRegions.withIndex()) {
                val k = c.trackB.problems[i]
                assertEquals(g.f("ref_start_s"), k.refStartS, "$name region $i: start")
                assertEquals(g.f("ref_end_s"), k.refEndS, "$name region $i: end")
                assertTrue(abs(g.f("severity") - k.severity) <= 0.001f,
                    "$name region $i: severity ${k.severity} != macOS ${g.f("severity")}")
                assertEquals(g.str("kind"), k.kind, "$name region $i: kind")
            }
        }
    }

    @Test
    fun track_b_result_matches_macos() {
        for (name in pairs) {
            val c = case(name)
            // tolerances per the manifest (the int8 drift budget); on this path
            // the inputs ARE the macOS golden, so agreement is much tighter.
            assertTrue(abs(c.golden.f("accuracy") - c.trackB.accuracy) <= 2.0f,
                "$name accuracy ${c.trackB.accuracy} vs macOS ${c.golden.f("accuracy")}")
            assertTrue(abs(c.golden.f("fluency") - c.trackB.fluency) <= 3.0f,
                "$name fluency ${c.trackB.fluency} vs macOS ${c.golden.f("fluency")}")
            assertTrue(abs(c.golden.f("speech_rate_ratio") - c.trackB.speechRateRatio) <= 0.001f,
                "$name rate ${c.trackB.speechRateRatio} vs macOS ${c.golden.f("speech_rate_ratio")}")
        }
    }

    @Test
    fun feedback_tips_match_macos_exactly() {
        for (name in pairs) {
            val c = case(name)
            val fb = json("pair/${name}_feedback.json")
            val got = generateFeedback(c.trackB, ProsodySummary(notes = fb.strList("prosody_notes")))
            val goldenTips = fb.strList("tips")

            assertEquals(goldenTips.size, got.tips.size,
                "$name: tip count — macOS $goldenTips, kotlin ${got.tips}")
            for (i in goldenTips.indices) {
                assertEquals(goldenTips[i], got.tips[i], "$name: tip $i")
            }
            assertEquals(fb.str("overall_band"), got.overallBand, "$name: overall band")
            assertTrue(abs(fb.f("overall_score") - got.overallScore) <= 0.1f,
                "$name: overall score ${got.overallScore} vs macOS ${fb.f("overall_score")}")
        }
    }

    @Test
    fun feedback_handles_missing_prosody() {
        // Track A may be unavailable (macOS passes prosody=None); the payload
        // must still be well-formed rather than throwing.
        val c = case("wrongtext")
        val got = generateFeedback(c.trackB, null)
        assertTrue(got.tips.isNotEmpty(), "tips must never be empty")
        assertEquals(c.trackB.accuracy, got.accuracy)
    }

    @Test
    fun prosody_notes_drive_their_tips() {
        // the note->tip rules only fire on the wrongtext/slow golden if Track A
        // reports them, and on this synthetic corpus it doesn't — so exercise
        // them directly, else the branches ship untested.
        val c = case("samevoice")
        val flat = generateFeedback(c.trackB, ProsodySummary(notes = listOf("intonation_flat")))
        assertTrue(flat.tips.any { it.contains("intonation is flatter") },
            "intonation_flat did not produce its tip: ${flat.tips}")

        val choppy = generateFeedback(c.trackB, ProsodySummary(notes = listOf("choppy")))
        assertTrue(choppy.tips.any { it.contains("paused more than the reference") },
            "choppy did not produce its tip: ${choppy.tips}")

        // "too_many_pauses" and "choppy" must not double up
        val both = generateFeedback(c.trackB,
            ProsodySummary(notes = listOf("too_many_pauses", "choppy")))
        assertEquals(1, both.tips.count { it.contains("paused more than the reference") },
            "pause tip emitted twice: ${both.tips}")
    }
}
