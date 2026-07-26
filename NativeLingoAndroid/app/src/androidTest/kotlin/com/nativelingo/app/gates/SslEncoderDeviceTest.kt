package com.nativelingo.app.gates

import android.os.SystemClock
import android.util.Log
import com.nativelingo.embed.Wav2Vec2Encoder
import com.nativelingo.embed.normalizeWav2Vec2
import com.nativelingo.models.ModelId
import com.nativelingo.scoring.align.dtwAlign
import com.nativelingo.scoring.norm.cmvn
import com.nativelingo.scoring.norm.normalizePair
import com.nativelingo.scoring.score.CalibrationLoader
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.math.abs
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * R-5 on real hardware.
 *
 * The desktop R-5 ran onnxruntime's *JVM* build on macOS/arm64. That verified
 * the export and the int8 quantization; it did not verify the runtime that
 * actually ships. `onnxruntime-android` is a different build with different
 * kernels — XNNPACK-backed on arm64, NEON dot-product paths for the int8 MatMul,
 * a different threadpool. Same graph, same weights, different arithmetic, and
 * this encoder is the one component whose output feeds a *calibrated* score:
 * `calibration.json` was fitted on macOS costs, so drift here does not show up
 * as an error, it shows up as a learner being told 78 instead of 82.
 *
 * Bars are R-5's own, unchanged: golden cosine ≥0.985 after CMVN, and the
 * speaker-invariance DTW cost ≤0.18. "Unchanged" is load-bearing here — the first
 * device run failed both of them with the int8-transformer export (0.98297 and
 * 0.18323), and the resolution was to change the *model* rather than the
 * criteria: the SSL encoder now ships fp16, which measures 0.990–0.997 and
 * 0.16917 on this hardware. Restating a bar to fit a measurement is the one move
 * that would have made every earlier R-5 number meaningless, so the bars stayed
 * and the ladder in the plan's §7 no-go was taken as written.
 * See SslPrecisionProbeDeviceTest for both rows side by side.
 */
@RunWith(AndroidJUnit4::class)
class SslEncoderDeviceTest {

    private val clips = listOf("ref_samantha", "crossvoice_daniel", "wrongtext_samantha", "slow_samantha")

    @Test
    fun normalization_matches_the_extractor_on_device() {
        // No model needed. Runs first because if the *input* differs, every cosine
        // below is measuring the wrong thing — and this is exactly the kind of
        // code that can differ per platform (Kotlin/JVM vs Android's ART, float
        // vs double accumulation in the variance).
        for (name in clips) {
            val mine = normalizeWav2Vec2(DeviceFixtures.float1d("wav/$name.npy"))
            val gold = DeviceFixtures.float1d("wav/${name}_input.npy")
            assertEquals(gold.size, mine.size, "$name length")
            val d = Numeric.maxAbsDiff(gold, mine)
            assertTrue(d < 1e-5, "$name normalization max-diff $d (need < 1e-5)")
        }
    }

    @Test
    fun onnx_android_embeddings_match_the_macos_golden() {
        val model = DeviceFixtures.requireModel(ModelId.SSL_ENCODER)
        Wav2Vec2Encoder(model.absolutePath).use { enc ->
            // Warmup excluded from the timings: first run pays graph optimisation
            // and arena allocation, and NFR-3 is about the second sentence onward.
            enc.runNormalized(DeviceFixtures.float1d("wav/${clips[0]}_input.npy"))

            for (name in clips) {
                val input = DeviceFixtures.float1d("wav/${name}_input.npy")
                val t0 = SystemClock.elapsedRealtimeNanos()
                val out = enc.runNormalized(input)
                val ms = (SystemClock.elapsedRealtimeNanos() - t0) / 1e6
                val cos = Numeric.cosAfterCmvn(out, DeviceFixtures.frames("emb/$name.npy"))
                Log.i(
                    DeviceFixtures.TAG,
                    "R-5 %-20s cos=%.6f  %d frames  %.0f ms (%.2fx realtime)".format(
                        name, cos, out.size, ms, (input.size / 16000.0) / (ms / 1000.0),
                    ),
                )
                assertTrue(cos >= 0.985, "$name: arm64 Android embedding cosine $cos < 0.985")
            }
        }
    }

    @Test
    fun speaker_invariance_survives_the_android_runtime() {
        // The touchstone. Two different voices saying the same sentence must stay
        // closer than the ±0.18 band, or FR-4's premise — that the score measures
        // pronunciation and not timbre — is false on this platform.
        //
        // The bar's provenance matters for reading a failure here, and this is the
        // assertion that actually failed on the first device run, so it is worth
        // being precise about what the numbers meant. macOS fp32 measures 0.1714
        // and the bar was set at 0.18; the int8-transformer export measured 0.1773
        // on desktop ORT and 0.18323 on arm64 — over the bar, with the calibrated
        // accuracy still 95.00 and 0.0032 of headroom before it would move.
        //
        // So the failure was real but not the failure it looks like: invariance had
        // not broken, the margin had. That is why the fix was fp16 (0.16917 here,
        // better than macOS fp32) and not a looser bar. Two thresholds that only
        // hold because a quantisation happened to land well are not thresholds. The
        // headroom logged below is the quantity that decision was made on, and is
        // logged every run so the next such decision has the same number available.
        val model = DeviceFixtures.requireModel(ModelId.SSL_ENCODER)
        Wav2Vec2Encoder(model.absolutePath).use { enc ->
            val ref = cmvn(enc.encode(DeviceFixtures.float1d("wav/ref_samantha.npy")))
            val cross = cmvn(enc.encode(DeviceFixtures.float1d("wav/crossvoice_daniel.npy")))
            val cost = dtwAlign(ref, cross).normalizedCost

            // Where this cost lands on the shipped isotonic curve, and how much
            // further it could drift before the curve answers differently. That
            // headroom is the quantity a threshold decision should be made on.
            val cal = CalibrationLoader.loadDefault()
            val acc = cal.accuracyFromCost(cost)
            var edge = cost
            while (edge < 0.95f && cal.accuracyFromCost(edge) >= acc - 1e-6f) edge += 0.0002f
            Log.i(
                DeviceFixtures.TAG,
                ("R-5 speaker-invariance cost = %.5f (bar ≤0.18; macOS fp32 0.1714, desktop int8 0.1773)  " +
                    "→ accuracy %.2f, unchanged until cost %.4f (headroom %.4f)").format(
                    cost, acc, edge, edge - cost,
                ),
            )
            assertTrue(cost <= 0.18, "speaker-invariance cost $cost > 0.18 on device")
        }
    }

    @Test
    fun the_pair_costs_the_calibrator_was_fitted_on_are_reproduced() {
        // The number that actually reaches the learner. `calibration.json` maps
        // cost→accuracy, and it was fitted on macOS costs; a cost that drifts past
        // the ±0.02 golden tolerance means the shipped calibration is being read
        // at the wrong place on its own curve.
        //
        // Same construction as TrackBParityTest: normalizePair (not per-clip
        // cmvn), and the ref/learner assignments the goldens were dumped with.
        val model = DeviceFixtures.requireModel(ModelId.SSL_ENCODER)
        Wav2Vec2Encoder(model.absolutePath).use { enc ->
            val embs = HashMap<String, Array<FloatArray>>()
            fun raw(name: String) = embs.getOrPut(name) {
                enc.encode(DeviceFixtures.float1d("wav/$name.npy"))
            }
            val pairs = listOf(
                Triple("samevoice", "ref_samantha", "ref_samantha"),
                Triple("speakervariance", "ref_samantha", "crossvoice_daniel"),
                Triple("slow", "ref_samantha", "slow_samantha"),
                Triple("wrongtext", "ref_samantha", "wrongtext_samantha"),
            )
            var worst = 0.0
            for ((tag, refName, learnerName) in pairs) {
                val want = (DeviceFixtures.assetJson("pair/$tag.json")["raw_path_cost"] as Number).toDouble()
                val (rn, ln) = normalizePair(raw(refName), raw(learnerName))
                val got = dtwAlign(rn, ln).normalizedCost.toDouble()
                val d = abs(want - got)
                worst = maxOf(worst, d)
                Log.i(DeviceFixtures.TAG, "R-5 pair %-16s cost %.5f vs macOS %.5f  Δ%.5f".format(tag, got, want, d))
                assertTrue(d <= 0.02, "$tag: DTW cost $got vs macOS $want (Δ$d > 0.02)")
            }
            Log.i(DeviceFixtures.TAG, "R-5 worst pair cost Δ = $worst (tolerance 0.02)")
        }
    }
}
