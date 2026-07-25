package com.nativelingo.scoring

import com.nativelingo.scoring.align.dtwAlign
import com.nativelingo.scoring.io.NpyReader
import com.nativelingo.scoring.io.frames2d
import com.nativelingo.scoring.io.frames2dInt
import com.nativelingo.scoring.norm.normalizePair
import com.nativelingo.scoring.score.CalibrationLoader
import com.nativelingo.scoring.score.scoreFluency
import kotlin.test.Test
import kotlin.test.assertEquals

/**
 * Gate A · Layer 1 — closes the cost→score loop: recompute accuracy (isotonic
 * on DTW cost) and fluency (path-deviation GAM) in Kotlin and assert they
 * match the macOS golden `accuracy` / `fluency` (95.0 / 74.5 / …).
 *
 * Accuracy runs end-to-end through the Kotlin DTW; fluency uses the macOS path
 * directly to isolate the GAM + path-deviation math from path-finding drift.
 */
class ScoreParityTest {

    private val accTol = 2.0 // manifest.json: tolerances.accuracy
    private val fluTol = 3.0 // manifest.json: tolerances.fluency
    private val calib by lazy { CalibrationLoader.loadDefault() }

    private val cases = listOf(
        Triple("samevoice", "ref_samantha", "ref_samantha"),
        Triple("speakervariance", "ref_samantha", "crossvoice_daniel"),
        Triple("wrongtext", "ref_samantha", "wrongtext_samantha"),
        Triple("slow", "ref_samantha", "slow_samantha"),
    )

    private fun golden(path: String) =
        javaClass.getResourceAsStream("/golden/$path")
            ?: error("missing golden resource: /golden/$path")

    private fun emb(name: String) = NpyReader.read(golden("emb/$name.npy")).frames2d()

    private fun field(file: String, field: String): Double {
        val txt = golden(file).bufferedReader().use { it.readText() }
        val m = Regex(""""$field":\s*([0-9.]+)""").find(txt)
            ?: error("$field not found in $file")
        return m.groupValues[1].toDouble()
    }

    private fun cost(ref: String, learner: String): Float {
        val (rn, ln) = normalizePair(emb(ref), emb(learner))
        return dtwAlign(rn, ln).normalizedCost
    }

    @Test
    fun accuracy_matches_macos() {
        for ((name, ref, lrn) in cases) {
            val expected = field("pair/$name.json", "accuracy")
            val actual = calib.accuracyFromCost(cost(ref, lrn)).toDouble()
            assertEquals(expected, actual, accTol,
                "accuracy drift on $name: expected $expected, got $actual")
        }
    }

    @Test
    fun fluency_matches_macos() {
        for ((name, ref, lrn) in cases) {
            val path = NpyReader.read(golden("pair/${name}_path.npy")).frames2dInt()
            val refLen = field("pair/${name}_fluency.json", "ref_len").toInt()
            val learnerLen = field("pair/${name}_fluency.json", "learner_len").toInt()
            val pausePerS = field("pair/${name}_fluency.json", "pause_per_s").toFloat()
            val pauseRatio = field("pair/${name}_fluency.json", "pause_ratio").toFloat()
            val expected = field("pair/$name.json", "fluency")
            val actual = scoreFluency(path, refLen, learnerLen, pausePerS, pauseRatio, calib)
                .first.toDouble()
            assertEquals(expected, actual, fluTol,
                "fluency drift on $name: expected $expected, got $actual")
        }
    }
}
