package com.nativelingo.app.gates

import android.app.ActivityManager
import android.content.Context
import android.os.Debug
import android.os.SystemClock
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nativelingo.align.ForcedAligner
import com.nativelingo.align.MmsEmitter
import com.nativelingo.embed.Wav2Vec2Encoder
import com.nativelingo.models.ModelCatalog
import com.nativelingo.models.ModelId
import com.nativelingo.scoring.align.dtwAlign
import com.nativelingo.scoring.norm.normalizePair
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/**
 * Gate D / R-8, **partial**: does the analyse path fit in a 6 GB device?
 *
 * The plan's criterion is peak RSS < 3.5 GB with 20 consecutive iterations and
 * no OOM. Two honest qualifications on this run:
 *
 *  1. **espeak is not exercised.** FR-11's `:core-mdd` is Phase 3 and does not
 *     exist yet, so the largest single model (302.9 MiB of int8 weights, and the
 *     one the plan expected to dominate) contributes only its file, not a
 *     session. This measures the floor, not the ceiling. Recorded as such —
 *     R-8 cannot be closed by this run.
 *  2. **The clip is 2.5 s, not 30 s.** Peak memory here is dominated by weights
 *     and ORT arenas rather than activations, but a 30 s clip's emission
 *     (T≈1500 × 29 floats) and the DTW cost matrix are not free either, so this
 *     under-measures the activation side.
 *
 * What it does establish, and what nothing before it could: all sessions of two
 * different ONNX Runtime builds open simultaneously in one process, held across
 * 20 iterations, on a device with a real 6 GB memory profile — and whether
 * anything grows per-iteration, which is the failure mode that a single run
 * cannot see and a leaked `OrtSession` produces.
 */
@RunWith(AndroidJUnit4::class)
class MemoryBudgetDeviceTest {

    private val iterations = 20
    private val budgetKb = 3_500 * 1024

    @Test
    fun the_device_profile_is_the_one_gate_d_is_about() {
        val am = DeviceFixtures.appContext.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val info = ActivityManager.MemoryInfo().also { am.getMemoryInfo(it) }
        val totalMib = info.totalMem / 1048576
        Log.i(
            DeviceFixtures.TAG,
            "R-8 device: totalMem=${totalMib}MiB avail=${info.availMem / 1048576}MiB " +
                "lowMemory=${info.lowMemory} largeHeap-class=${am.largeMemoryClass}MiB " +
                "isLowRamDevice=${am.isLowRamDevice}",
        )
        // Recorded, not gated — the gate is about the memory *we* use. But a run on
        // a 12 GB device tells us nothing about NFR-4③, so the profile has to be in
        // the record next to the number.
        assertTrue(totalMib > 0)
    }

    @Test
    fun all_sessions_coexist_across_twenty_iterations_within_the_budget() {
        val ssl = DeviceFixtures.requireModel(ModelId.SSL_ENCODER)
        val mms = DeviceFixtures.requireModel(ModelId.MMS_ALIGNER)
        // Present but not loaded — see the class doc. Resolving it still matters:
        // Gate D's premise is that this file is on the device at analyse time.
        DeviceFixtures.requireModel(ModelId.ESPEAK_MDD)

        val words = "The quick brown fox jumps over the lazy dog.".trimEnd('.').split(" ")
        val ref = DeviceFixtures.float1d("wav/ref_samantha.npy")
        val learner = DeviceFixtures.float1d("wav/slow_samantha.npy")

        var peakKb = 0
        var afterWarmupKb = 0
        val timings = ArrayList<Long>(iterations)

        fun pss(label: String): Int {
            val mi = Debug.MemoryInfo().also { Debug.getMemoryInfo(it) }
            val kb = mi.totalPss
            peakKb = maxOf(peakKb, kb)
            Log.i(
                DeviceFixtures.TAG,
                "R-8 %-22s PSS=%.0fMiB (native=%.0f dalvik=%.0f)".format(
                    label, kb / 1024.0, mi.nativePss / 1024.0, mi.dalvikPss / 1024.0,
                ),
            )
            return kb
        }

        pss("before any session")

        Wav2Vec2Encoder(ssl.absolutePath).use { enc ->
            pss("ssl session open")
            MmsEmitter(mms.absolutePath).use { emitter ->
                pss("+ mms session open")
                val aligner = ForcedAligner(emitter)

                // One warmup iteration, then baseline: ORT grows its arenas on the
                // first run, so comparing iteration 2 against iteration 1 would
                // report normal arena growth as a leak.
                runOnce(enc, aligner, words, ref, learner)
                afterWarmupKb = pss("after warmup iteration")

                for (i in 1..iterations) {
                    val t0 = SystemClock.elapsedRealtime()
                    runOnce(enc, aligner, words, ref, learner)
                    timings.add(SystemClock.elapsedRealtime() - t0)
                    if (i % 5 == 0 || i == iterations) pss("iteration $i")
                }
            }
        }

        val finalKb = pss("all sessions closed")
        val growthKb = peakKb - afterWarmupKb
        Log.i(
            DeviceFixtures.TAG,
            ("R-8 peak PSS = %.0f MiB (budget %.0f) | post-warmup %.0f | growth over %d iters %.1f MiB " +
                "| after close %.0f | per-iteration %d..%d ms (median %d)").format(
                peakKb / 1024.0, budgetKb / 1024.0, afterWarmupKb / 1024.0, iterations, growthKb / 1024.0,
                finalKb / 1024.0, timings.min(), timings.max(), timings.sorted()[timings.size / 2],
            ),
        )
        Log.i(
            DeviceFixtures.TAG,
            "R-8 NOT measured this round: espeak inference (Phase 3 :core-mdd), " +
                "whisper session held concurrently, 30s clips. " +
                "Weights on device: %.0f MiB.".format(ModelCatalog.INSTALL_TIME_BYTES / 1048576.0),
        )

        assertTrue(peakKb < budgetKb, "peak PSS ${peakKb / 1024} MiB exceeds the ${budgetKb / 1024} MiB budget")
        // A leak is the thing 20 iterations exist to find. 96 MiB over 20 runs of a
        // 2.5 s clip would be ~5 MiB per sentence — nothing a real session survives.
        assertTrue(
            growthKb < 96 * 1024,
            "PSS grew ${growthKb / 1024} MiB over $iterations iterations — something is not being released",
        )
    }

    /** One sentence through the parts of the analyse path that exist today. */
    private fun runOnce(
        enc: Wav2Vec2Encoder,
        aligner: ForcedAligner,
        words: List<String>,
        ref: FloatArray,
        learner: FloatArray,
    ) {
        val spans = aligner.align(words, ref)
        assertNotNull(spans, "alignment failed mid-loop")
        val (rn, ln) = normalizePair(enc.encode(ref), enc.encode(learner))
        dtwAlign(rn, ln)
    }
}
