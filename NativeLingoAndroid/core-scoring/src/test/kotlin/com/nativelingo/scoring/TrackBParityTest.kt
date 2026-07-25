package com.nativelingo.scoring

import com.nativelingo.scoring.align.dtwAlign
import com.nativelingo.scoring.io.NpyReader
import com.nativelingo.scoring.io.frames2d
import com.nativelingo.scoring.norm.normalizePair
import kotlin.test.Test
import kotlin.test.assertEquals

/**
 * Gate A · Layer 1 numerical-parity test: re-run the macOS Track-B scoring path
 * (CMVN → banded DTW) on the macOS-dumped embeddings and assert the mean path
 * cost matches the macOS golden `raw_path_cost` within tolerance.
 *
 * This is the JVM proof that the scoring core is portable byte-for-byte
 * (within int8-free tolerance) before any ONNX/mobile work. The speaker-
 * invariance pair is the existence-proof touchstone: different voices reading
 * the same text must stay low-cost (macOS: 0.1714).
 */
class TrackBParityTest {

    private val costTol = 0.02 // manifest.json: tolerances.dtw_cost

    private fun golden(path: String) =
        javaClass.getResourceAsStream("/golden/$path")
            ?: error("missing golden resource: /golden/$path")

    private fun emb(name: String) = NpyReader.read(golden("emb/$name.npy")).frames2d()

    private fun pairCost(name: String): Double {
        // read raw_path_cost without pulling a JSON dependency into :core-scoring
        val txt = golden("pair/$name.json").bufferedReader().use { it.readText() }
        val m = Regex(""""raw_path_cost":\s*([0-9.]+)""").find(txt)
            ?: error("raw_path_cost not found in pair/$name.json")
        return m.groupValues[1].toDouble()
    }

    private fun cost(ref: String, learner: String): Float {
        val (rn, ln) = normalizePair(emb(ref), emb(learner))
        return dtwAlign(rn, ln).normalizedCost
    }

    @Test
    fun speaker_invariance_cost_matches_macos() {
        // THE Gate A touchstone (docs/android-migration.md §7): cross-voice
        // same-text cost must stay ≤0.18; here we assert parity with macOS (0.1714).
        val expected = pairCost("speakervariance")
        val actual = cost("ref_samantha", "crossvoice_daniel")
        assertEquals(expected, actual.toDouble(), costTol,
            "speaker-invariance cost drifted from macOS golden (expected $expected, got $actual)")
    }

    @Test
    fun samevoice_cost_matches_macos() {
        assertEquals(pairCost("samevoice"),
            cost("ref_samantha", "ref_samantha").toDouble(), costTol)
    }

    @Test
    fun wrongtext_cost_matches_macos() {
        assertEquals(pairCost("wrongtext"),
            cost("ref_samantha", "wrongtext_samantha").toDouble(), costTol)
    }
}
