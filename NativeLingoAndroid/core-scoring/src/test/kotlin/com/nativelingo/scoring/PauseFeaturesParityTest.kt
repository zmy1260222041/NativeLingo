package com.nativelingo.scoring

import com.nativelingo.scoring.audio.AudioPreproc
import com.nativelingo.scoring.audio.PauseFeatures
import com.nativelingo.scoring.io.NpyReader
import com.nativelingo.scoring.io.toFloatArray1d
import kotlin.math.PI
import kotlin.math.sin
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Gate A · pause-feature extraction — the piece `scoreTrackB` needs that
 * `:core-scoring` did not have until M0. The macOS golden fluency fixtures
 * (`golden/pair/<name>_fluency.json`) carry the values Praat computed, but nothing
 * in Kotlin computed them — the fluency parity test in `ScoreParityTest` read
 * them straight from JSON. This test closes that gap: compute them from the
 * waveforms and assert against what Praat measured.
 */
class PauseFeaturesParityTest {

    private fun golden(path: String) =
        javaClass.getResourceAsStream("/golden/$path")
            ?: error("missing golden resource: /golden/$path")

    private fun wav(name: String): FloatArray =
        NpyReader.read(golden("wav/$name.npy")).toFloatArray1d()

    /**
     * The four macOS-`say` clips the fluency golden set is built on. Praat's
     * `extract_prosody` measured ZERO pauses in each — `golden/pair/<name>_fluency.json`
     * all carry `pause_per_s=0.0, pause_ratio=0.0`. Clean synthetic speech has no
     * silent runs ≥ 0.15 s, so the RMS detector agrees exactly. That agreement is
     * the assertion: a detector that invents pauses in clean speech would shift
     * the fluency GAM for no physical reason.
     */
    private val clips = listOf(
        "ref_samantha",
        "crossvoice_daniel",
        "wrongtext_samantha",
        "slow_samantha",
    )

    @Test
    fun clean_synthetic_clips_have_no_pauses_like_praat() {
        for (name in clips) {
            val (pausePerS, pauseRatio) = PauseFeatures.fluencyInputs(wav(name))
            assertEquals(0.0, pausePerS, 0.0,
                "$name: expected 0 pauses/sec (Praat measured 0), got $pausePerS")
            assertEquals(0.0, pauseRatio, 0.0,
                "$name: expected 0 pause ratio (Praat measured 0), got $pauseRatio")
        }
    }

    /**
     * The positive case the all-zero golden set cannot cover: a real
     * mid-utterance silence ≥ [PauseFeatures.MIN_PAUSE_S] must register as one
     * pause, and a gap just under the floor must not. Built synthetically so it
     * does not lean on Praat — the same threshold-straddling pattern
     * `AudioPreprocParityTest` uses for the trim −30 dB line. Only the count and
     * the floor are asserted; the exact duration is framing-boundary-dependent
     * (a frame straddling the tone/gap edge counts silent when its tone portion
     * is tiny), so an exact-duration assertion would test the boundary math
     * rather than the threshold semantics.
     */
    @Test
    fun a_silence_run_over_threshold_counts_and_a_shorter_one_does_not() {
        val sr = AudioPreproc.TARGET_SR
        fun tone(n: Int) = FloatArray(n) { (0.6 * sin(2.0 * PI * 220.0 * it / sr)).toFloat() }
        fun withGap(gapS: Double) =
            tone(sr / 4) + FloatArray((gapS * sr).toInt()) + tone(sr / 4) // 0.25 s, gap, 0.25 s

        val over = PauseFeatures.extract(withGap(0.30), sr) // 0.30 s ≫ 0.15 floor
        assertEquals(1, over.numPauses, "a 0.30 s mid-utterance gap should register as one pause")
        assertTrue(over.totalPauseS >= PauseFeatures.MIN_PAUSE_S,
            "pause duration should reach the floor (got ${over.totalPauseS} s)")

        val under = PauseFeatures.extract(withGap(0.05), sr) // 0.05 s < floor
        assertEquals(0, under.numPauses, "a 0.05 s gap is below MIN_PAUSE_S and must not count")
    }
}
