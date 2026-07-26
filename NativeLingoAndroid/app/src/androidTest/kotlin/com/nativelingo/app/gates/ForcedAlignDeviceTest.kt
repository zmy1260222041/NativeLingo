package com.nativelingo.app.gates

import android.os.SystemClock
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nativelingo.align.ForcedAligner
import com.nativelingo.align.MmsEmitter
import com.nativelingo.align.alignWords
import com.nativelingo.align.normalizeWaveform
import com.nativelingo.models.ModelId
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.math.abs
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/**
 * R-6 on real hardware: MMS forced alignment on arm64 Android.
 *
 * What rides on this: word boundaries. FR-8's A/B replay seeks to them, FR-6's
 * per-word breakdown is projected onto them, and FR-11 crops its phoneme window
 * with them. A boundary that moves by 40 ms makes a replay clip that starts
 * mid-consonant — the learner hears the bug directly, unlike a score drift.
 *
 * Layered like the JVM test so a failure localises: the pure-Kotlin Viterbi over
 * the *golden* emission must be exact (no model involved, so no excuse for
 * drift), and only the ONNX run gets the 1-frame budget.
 */
@RunWith(AndroidJUnit4::class)
class ForcedAlignDeviceTest {

    private val sentence = "The quick brown fox jumps over the lazy dog."
    private val words = sentence.trimEnd('.').split(" ")

    private fun spansGolden() = DeviceFixtures.assetJson("mms/ref_samantha_spans.json")

    @Test
    fun viterbi_over_the_golden_emission_is_exact_on_arm() {
        // Doubles all the way through on the desktop; ART must agree bit-for-bit
        // in the decisions, not merely closely. A tie broken the other way moves a
        // boundary by a frame with no numeric drift to blame — this is why the tie
        // handling was pinned separately in scripts/verify_ctc_tiebreak.py.
        val em = DeviceFixtures.frames("mms/ref_samantha_emission.npy")
        val wav = DeviceFixtures.float1d("wav/ref_samantha.npy")
        val g = spansGolden()
        assertEquals((g["nframes"] as Number).toInt(), em.size, "golden emission frames")

        val got = alignWords(words, em, wav.size)
        assertNotNull(got, "alignment returned null on the golden emission")

        @Suppress("UNCHECKED_CAST")
        val goldenSpans = g["spans"] as List<Map<String, Any?>>
        assertEquals(goldenSpans.size, got.count { it != null }, "aligned word count")
        for ((i, gw) in goldenSpans.withIndex()) {
            val k = assertNotNull(got[i], "word ${gw["word"]} unaligned")
            assertEquals(round3((gw["start"] as Number).toFloat()), k.startS, "${gw["word"]}: start")
            assertEquals(round3((gw["end"] as Number).toFloat()), k.endS, "${gw["word"]}: end")
        }
    }

    @Test
    fun waveform_layer_norm_matches_torchaudio_on_device() {
        val mine = normalizeWaveform(DeviceFixtures.float1d("wav/ref_samantha.npy"))
        val gold = DeviceFixtures.float1d("mms/ref_samantha_wav_normalized.npy")
        assertEquals(gold.size, mine.size, "length")
        val d = Numeric.maxAbsDiff(gold, mine)
        assertTrue(d < 1e-5, "waveform layer_norm max-diff $d (need < 1e-5)")
    }

    @Test
    fun the_int8_emission_matches_torchaudio_frame_by_frame() {
        // Layer 2 (migration §"验证策略"): emission cosine ≥0.995. Checked before
        // the spans, because spans can be right while the emission is wrong —
        // argmax is forgiving, and the next model to reuse this emission (FR-11's
        // gating maths) is not.
        val model = DeviceFixtures.requireModel(ModelId.MMS_ALIGNER)
        MmsEmitter(model.absolutePath).use { emitter ->
            val t0 = SystemClock.elapsedRealtime()
            val em = emitter.emission(DeviceFixtures.float1d("wav/ref_samantha.npy"))
            val ms = SystemClock.elapsedRealtime() - t0
            val gold = DeviceFixtures.frames("mms/ref_samantha_emission.npy")
            assertEquals(gold.size, em.size, "frame count")
            assertEquals(gold[0].size, em[0].size, "emission width (29 = 28 + star)")
            val cos = Numeric.cosRaw(em, gold)
            Log.i(DeviceFixtures.TAG, "R-6 emission cos=%.6f, %d frames, %d ms".format(cos, em.size, ms))
            assertTrue(cos >= 0.995, "MMS emission cosine $cos < 0.995 on arm64 Android")
        }
    }

    @Test
    fun end_to_end_word_boundaries_stay_within_one_frame_of_macos() {
        val model = DeviceFixtures.requireModel(ModelId.MMS_ALIGNER)
        val g = spansGolden()
        val spf = (g["spf"] as Number).toFloat()
        val wav = DeviceFixtures.float1d("wav/ref_samantha.npy")

        MmsEmitter(model.absolutePath).use { emitter ->
            val got = ForcedAligner(emitter).align(words, wav)
            assertNotNull(got, "end-to-end alignment returned null")

            @Suppress("UNCHECKED_CAST")
            val goldenSpans = g["spans"] as List<Map<String, Any?>>
            var maxFrameErr = 0.0f
            for ((i, gw) in goldenSpans.withIndex()) {
                val k = assertNotNull(got[i], "${gw["word"]}: unaligned")
                val ds = abs((gw["start"] as Number).toFloat() - k.startS) / spf
                val de = abs((gw["end"] as Number).toFloat() - k.endS) / spf
                maxFrameErr = maxOf(maxFrameErr, ds, de)
                Log.i(
                    DeviceFixtures.TAG,
                    "R-6 %-6s [%.3f,%.3f] vs macOS [%.3f,%.3f]  Δ%.2f/%.2f frames".format(
                        gw["word"], k.startS, k.endS,
                        (gw["start"] as Number).toFloat(), (gw["end"] as Number).toFloat(), ds, de,
                    ),
                )
            }
            Log.i(DeviceFixtures.TAG, "R-6 worst boundary drift = $maxFrameErr frames (bar ≤1)")
            assertTrue(maxFrameErr <= 1.0f, "word boundaries drift $maxFrameErr frames (Gate B bar: ≤1)")
        }
    }

    private fun round3(x: Float): Float = (Math.rint(x.toDouble() * 1000.0) / 1000.0).toFloat()
}
