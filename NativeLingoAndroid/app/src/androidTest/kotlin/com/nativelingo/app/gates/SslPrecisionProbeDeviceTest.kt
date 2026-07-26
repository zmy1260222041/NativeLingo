package com.nativelingo.app.gates

import android.os.SystemClock
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nativelingo.embed.Wav2Vec2Encoder
import com.nativelingo.scoring.align.dtwAlign
import com.nativelingo.scoring.norm.cmvn
import com.nativelingo.scoring.norm.normalizePair
import com.nativelingo.scoring.score.CalibrationLoader
import org.junit.Assume
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * Why the SSL encoder ships fp16 and not int8, in numbers, on this device.
 *
 * R-5's no-go ladder named fp16 as the fallback if int8 broke Track B, and the
 * device run triggered it: arm64 int8 kernels put speaker invariance at 0.18323
 * against the ≤0.18 bar and the worst golden cosine at 0.98297 against ≥0.985 —
 * both just past, in the same direction, with the calibrated accuracy unmoved at
 * 95.00 but only 0.0032 of cost headroom left before it would move (0.0155 at
 * fp32). fp16 measures 0.16917 and 0.990–0.997 on the same hardware, better than
 * macOS fp32's own 0.1714, for +43.9 MiB and half the throughput. The user chose
 * fp16 over restating the criteria; this test is what makes that choice auditable
 * instead of a claim in a review, and what would notice if a later ORT or export
 * changed the trade.
 *
 * Getting the fp16 side measured at all took two fixes, both worth knowing about
 * because both were invisible until a real device ran the file. The export was
 * unloadable — `onnxconverter_common.float16` emitted an fp16 tensor from a Cast
 * still declaring fp32 — and once that was fixed with ORT's maintained fork, ORT
 * on Android refused it: its load-time optimizer fuses the graph's 17 `Erf`s into
 * `com.microsoft.Gelu`, for which the *pruned mobile build* has no fp16 kernel
 * where desktop does. Holding Erf in fp32 breaks the fusion pattern. Neither
 * failure was reachable from the desktop, which is the general lesson.
 *
 * Unlike the gate suites this one *does* skip when its comparison model is
 * absent, and the distinction is deliberate. A gate that skips itself launders a
 * missing measurement into a green tick. This reports a comparison; the int8
 * export is deliberately not in `ModelCatalog` (it is the rejected candidate), so
 * its absence is the normal case and not a gap in coverage.
 *
 * ```
 * scripts/push_device_models.sh --with-int8
 * scripts/run_device_gates.sh --skip-build -c ...gates.SslPrecisionProbeDeviceTest
 * ```
 */
@RunWith(AndroidJUnit4::class)
class SslPrecisionProbeDeviceTest {

    /** Not resolved through ModelRegistry: the int8 export is not in the catalog. */
    private fun int8OrSkip(): String {
        val f = File(DeviceFixtures.modelDir, "w2v2_base_69_int8_transformer.onnx")
        Assume.assumeTrue(
            "int8 encoder not on device — push it with scripts/push_device_models.sh --with-int8",
            f.isFile && f.length() > 0,
        )
        return f.absolutePath
    }

    @Test
    fun the_shipped_fp16_encoder_beats_the_int8_one_it_replaced() {
        val int8 = int8OrSkip()
        val fp16 = DeviceFixtures.requireModel(com.nativelingo.models.ModelId.SSL_ENCODER)
        val clips = listOf("ref_samantha", "crossvoice_daniel", "wrongtext_samantha", "slow_samantha")
        val cal = CalibrationLoader.loadDefault()

        for ((label, path) in listOf("int8-transformer" to int8, "fp16 (shipped)" to fp16.absolutePath)) {
            Wav2Vec2Encoder(path).use { enc ->
                val embs = HashMap<String, Array<FloatArray>>()
                // One warmup encode before timing: the first run pays ORT's arena
                // growth and kernel selection, which is not what per-clip latency
                // means for FR-4.
                enc.encode(DeviceFixtures.float1d("wav/ref_samantha.npy"))

                var totalMs = 0.0
                var totalS = 0.0
                for (name in clips) {
                    val wav = DeviceFixtures.float1d("wav/$name.npy")
                    val t0 = SystemClock.elapsedRealtimeNanos()
                    val out = enc.encode(wav)
                    totalMs += (SystemClock.elapsedRealtimeNanos() - t0) / 1e6
                    totalS += wav.size / 16000.0
                    embs[name] = out
                }

                // Layer-2 cosine against the macOS fp32 golden.
                //
                // Via `runNormalized` on the pre-normalised `_input.npy`, which is
                // what the failing assertion in SslEncoderDeviceTest does — not
                // `encode` on the raw wav, even though the two differ by under 1e-5
                // of input (that test's first case asserts exactly this). The point
                // of the probe is to put the fp16 number beside the int8 number that
                // failed, so the instrument has to be the same one, not an
                // equivalent one.
                val cosines = clips.associateWith { name ->
                    Numeric.cosAfterCmvn(
                        enc.runNormalized(DeviceFixtures.float1d("wav/${name}_input.npy")),
                        DeviceFixtures.frames("emb/$name.npy"),
                    )
                }

                // The touchstone, and where the shipped calibration reads it.
                val invariance = dtwAlign(
                    cmvn(embs["ref_samantha"]!!), cmvn(embs["crossvoice_daniel"]!!),
                ).normalizedCost
                val acc = cal.accuracyFromCost(invariance)
                var edge = invariance
                while (edge < 0.95f && cal.accuracyFromCost(edge) >= acc - 1e-6f) edge += 0.0002f

                // Every pair the calibrator was fitted on, so a precision change
                // cannot fix invariance by quietly moving something else.
                val pairs = listOf(
                    Triple("samevoice", "ref_samantha", "ref_samantha"),
                    Triple("speakervariance", "ref_samantha", "crossvoice_daniel"),
                    Triple("slow", "ref_samantha", "slow_samantha"),
                    Triple("wrongtext", "ref_samantha", "wrongtext_samantha"),
                )
                val pairCosts = pairs.associate { (key, r, l) ->
                    val (a, b) = normalizePair(embs[r]!!, embs[l]!!)
                    key to dtwAlign(a, b).normalizedCost
                }

                Log.i(
                    DeviceFixtures.TAG,
                    ("R-5/probe %-16s invariance=%.5f → acc %.2f (headroom %.4f)  " +
                        "cos %.6f..%.6f  %.0f ms for %.2fs (%.1fx realtime)  size %.1f MiB").format(
                        label, invariance, acc, edge - invariance,
                        cosines.values.min(), cosines.values.max(),
                        totalMs, totalS, totalS / (totalMs / 1000.0),
                        File(path).length() / 1048576.0,
                    ),
                )
                Log.i(
                    DeviceFixtures.TAG,
                    "R-5/probe %-16s pairs %s".format(
                        label,
                        pairCosts.entries.joinToString("  ") { "%s=%.5f".format(it.key, it.value) },
                    ),
                )
                for ((name, c) in cosines) {
                    Log.i(DeviceFixtures.TAG, "R-5/probe %-16s %-20s cos=%.6f".format(label, name, c))
                }
            }
        }
        // Deliberately no assertion on the *comparison*. Which precision ships is
        // a product decision with a size and latency price, not something a test
        // gets to relitigate; SslEncoderDeviceTest is where the shipped encoder
        // has to clear R-5's actual bars. What this adds is the record of what the
        // alternative measured on the same hardware in the same run.
    }
}
