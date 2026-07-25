package com.nativelingo.scoring

import com.nativelingo.scoring.io.NpyReader
import com.nativelingo.scoring.resample.PolyphaseResampler
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.sin
import kotlin.math.PI
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * R-9 / Gate E parity: `PolyphaseResampler` vs `scipy.signal.resample_poly`.
 *
 * The gate itself is a score-domain claim (swapping the reference's resampler
 * moves the DTW cost by ≤0.0011) and was measured on the desktop with
 * `scripts/resampler_parity.py`. That measurement only transfers to Android if
 * the Kotlin resampler is the same filter that was measured — which is what
 * these tests pin, sample by sample.
 *
 * Fixtures: `golden/resample/` (see `scripts/capture_golden.py:dump_resample`),
 * float64 on both sides. The production path is float32; it is checked here too,
 * but against an SNR bound rather than the same tolerance, because float32
 * accumulation order is not something a port can or should reproduce.
 */
class PolyphaseResamplerParityTest {

    private fun golden(name: String) =
        javaClass.getResourceAsStream("/golden/resample/$name")
            ?: error("missing golden resource: /golden/resample/$name")

    private fun double1d(name: String): DoubleArray = NpyReader.read(golden(name)).data

    private fun meta() = TestJson.obj(golden("resample.json").reader().readText())

    private fun snrDb(ref: DoubleArray, got: DoubleArray): Double {
        var sig = 0.0
        var err = 0.0
        for (i in ref.indices) {
            sig += ref[i] * ref[i]
            val e = ref[i] - got[i]
            err += e * e
        }
        return if (err == 0.0) Double.POSITIVE_INFINITY else 10.0 * log10(sig / err)
    }

    @Test
    fun every_golden_case_matches_scipy_resample_poly_sample_for_sample() {
        val cases = meta().objList("cases")
        assertEquals(4, cases.size, "fixture case count")
        for (c in cases) {
            val name = c.str("name")
            val x = double1d("${name}_in.npy")
            val expected = double1d("${name}_out.npy")
            assertEquals(c.int("n_in"), x.size, "$name: fixture input length")

            val got = PolyphaseResampler.resample(x, c.int("sr_in"), c.int("sr_out"))
            assertEquals(c.int("n_out"), got.size, "$name: output length")
            assertEquals(expected.size, got.size, "$name: output length vs golden")

            var worst = 0.0
            var at = -1
            for (i in expected.indices) {
                val d = abs(expected[i] - got[i])
                if (d > worst) { worst = d; at = i }
            }
            // 1e-12 is ~4 orders above the double round-off of an 8821-tap sum
            // and ~10 orders below the signal, so it fails on a real algorithmic
            // difference and on nothing else.
            assertTrue(
                worst < 1e-12,
                "$name: max |Δ| = $worst at sample $at (SNR ${snrDb(expected, got)} dB)",
            )
        }
    }

    @Test
    fun the_filter_design_reproduces_scipys_firwin_kaiser_invariants() {
        val m = meta()
        assertEquals(
            PolyphaseResampler.KAISER_BETA,
            ((m["design"] as Map<*, *>)["kaiser_beta"] as Number).toDouble(),
            "beta",
        )
        // scipy applies `scale=True` at DC for a pass-zero band, so the
        // *unscaled* design has unit DC gain. Getting this wrong is a pure gain
        // error, invisible in a waveform plot and fatal to a calibrated score.
        for ((numtaps, cutoff) in listOf(61 to 1.0 / 3, 8821 to 1.0 / 441, 21 to 0.25)) {
            val h = PolyphaseResampler.designFilter(numtaps, cutoff)
            assertEquals(1.0, h.sum(), 1e-12, "DC gain, numtaps=$numtaps")
            // Linear phase: the design is symmetric.
            for (i in 0 until numtaps / 2) {
                assertEquals(h[i], h[numtaps - 1 - i], 1e-15, "symmetry at $i")
            }
        }
        // numpy.kaiser endpoints and centre, beta=5.0.
        val w = PolyphaseResampler.kaiser(9, 5.0)
        assertEquals(1.0 / PolyphaseResampler.besselI0(5.0), w[0], 1e-15, "kaiser endpoint")
        assertEquals(1.0, w[4], 1e-15, "kaiser centre")
        assertEquals(w[0], w[8], 1e-15, "kaiser symmetry")
        // i0(0)=1, i0(1)=1.2660658777520084, i0(5)=27.239871823604442 (scipy).
        assertEquals(1.0, PolyphaseResampler.besselI0(0.0), 1e-15)
        assertEquals(1.2660658777520084, PolyphaseResampler.besselI0(1.0), 1e-13)
        assertEquals(27.239871823604442, PolyphaseResampler.besselI0(5.0), 1e-11)
    }

    @Test
    fun a_tone_below_nyquist_survives_and_one_above_it_is_stopped() {
        // Independent of the golden: an analytic check that the thing actually
        // resamples rather than merely agreeing with a fixture. 0.5 s at 48 kHz.
        val srIn = 48_000
        val srOut = 16_000
        val n = srIn / 2
        fun tone(f: Double, sr: Int, len: Int) =
            DoubleArray(len) { sin(2 * PI * f * it / sr) }

        val passband = PolyphaseResampler.resample(tone(1000.0, srIn, n), srIn, srOut)
        // Compare against the analytically resampled tone, away from the edges
        // where the FIR is still filling.
        val guard = 200
        var num = 0.0
        var den = 0.0
        for (i in guard until passband.size - guard) {
            val want = sin(2 * PI * 1000.0 * i / srOut)
            num += want * want
            den += (want - passband[i]) * (want - passband[i])
        }
        val snr = 10.0 * log10(num / den)
        assertTrue(snr > 40.0, "1 kHz passband SNR was $snr dB")

        // 11 kHz is above the 8 kHz output Nyquist: it must be attenuated, not
        // folded back to 5 kHz at full amplitude.
        val stopped = PolyphaseResampler.resample(tone(11_000.0, srIn, n), srIn, srOut)
        var peak = 0.0
        for (i in guard until stopped.size - guard) peak = max(peak, abs(stopped[i]))
        assertTrue(peak < 0.02, "11 kHz alias leaked at amplitude $peak (input 1.0)")
    }

    @Test
    fun the_float32_path_tracks_the_float64_one() {
        val x = double1d("speech_44k1_in.npy")
        val ref = PolyphaseResampler.resample(x, 44_100, 16_000)
        val f32 = PolyphaseResampler.resampleRatio(FloatArray(x.size) { x[it].toFloat() }, 160, 441)
        assertEquals(ref.size, f32.size, "float32 output length")
        val snr = snrDb(ref, DoubleArray(f32.size) { f32[it].toDouble() })
        assertTrue(snr > 100.0, "float32 vs float64 SNR was $snr dB")
    }

    @Test
    fun degenerate_inputs_do_not_throw() {
        assertEquals(0, PolyphaseResampler.resample(DoubleArray(0), 44_100, 16_000).size)
        // Equal rates short-circuit; and the two entry points agree — note the
        // reversed argument order, which is exactly why they have distinct names.
        val x = DoubleArray(1000) { cos(it * 0.01) }
        assertTrue(PolyphaseResampler.resample(x, 16_000, 16_000).contentEquals(x))
        assertTrue(
            PolyphaseResampler.resampleRatio(x, 160, 441)
                .contentEquals(PolyphaseResampler.resample(x, 44_100, 16_000)),
        )
        // One input sample: scipy yields ceil(1*up/down) outputs.
        assertEquals(1, PolyphaseResampler.resample(doubleArrayOf(1.0), 48_000, 16_000).size)
    }
}
