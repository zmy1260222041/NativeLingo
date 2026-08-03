package com.nativelingo.app.gates

import android.os.SystemClock
import android.util.Log
import com.nativelingo.models.ModelCatalog
import org.junit.Test
import org.junit.runner.RunWith
import androidx.test.ext.junit.runners.AndroidJUnit4
import java.io.File
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The precondition every other gate test depends on: the weights on this device
 * are byte-for-byte the artifacts the desktop gates were measured on.
 *
 * Without this, a failure anywhere below is ambiguous between "arm64 kernels
 * differ" and "the push was truncated / the wrong export got copied", and the
 * second is by far the more likely. It also produces the first real NFR-3
 * datapoint for the warmup path: how long a full-set checksum actually takes on
 * device storage.
 *
 * Cloud architecture (v0.7): the set is 2 models now — the Speaking track's
 * whisper/VAD/MMS/espeak moved to the server, so their absence here is the
 * *desired* state, asserted as such.
 */
@RunWith(AndroidJUnit4::class)
class ModelIntegrityDeviceTest {

    @Test
    fun install_time_set_is_present_and_hashes_match_the_catalog() {
        DeviceFixtures.logPresentModels()

        // resolve() first, so a missing/truncated file reports as such with the
        // push command instead of as a hash mismatch 40 seconds later.
        for (spec in ModelCatalog.installTime) DeviceFixtures.requireModel(spec.id)

        // Clear the markers first, or this measures nothing.
        //
        // `verify` memoises per file into `model-state/<name>.verified`, and both
        // the marker directory and the models survive a harness run — that is the
        // whole point of scripts/run_device_gates.sh not uninstalling. So on every
        // run after the first, `verifyAll` returned from the marker and this test
        // logged `SHA-256 over 182.8 MiB took 0 ms (Infinity MiB/s)`: a hash rate
        // for a hash that never ran, stated as the NFR-3 warmup datapoint it is
        // supposed to produce. The `Infinity` was the only visible tell, and
        // `assertTrue(ms > 0)` was one scheduling accident away from catching it.
        val cleared = DeviceFixtures.stateDir.listFiles()
            ?.count { it.name.endsWith(".verified") && it.delete() } ?: 0
        // Asserted structurally rather than by timing. The first attempt gated on
        // `ms > 1000` — "935 MiB of SHA-256 cannot happen in under a second on any
        // storage this app will meet" — and that was simply false here: the
        // emulator's files were still in the host's page cache and it hashed them
        // in 460 ms at 2033 MiB/s. Guessing a floor for storage that has not been
        // measured is how the original bug got in. What can be established directly
        // is that no marker survived.
        val live = ModelCatalog.installTime.filter {
            File(DeviceFixtures.stateDir, "${it.fileName}.verified").isFile
        }
        assertTrue(live.isEmpty(), "markers survived deletion: ${live.map { it.fileName }}")

        val t0 = SystemClock.elapsedRealtime()
        var lastPct = -1
        DeviceFixtures.registry.verifyAll(ModelCatalog.installTime) { done, total ->
            val pct = (done * 100 / total).toInt()
            if (pct / 10 != lastPct / 10) {
                Log.i(DeviceFixtures.TAG, "verify $pct% ($done/$total B)")
                lastPct = pct
            }
        }
        val ms = SystemClock.elapsedRealtime() - t0
        val mib = ModelCatalog.TOTAL_BYTES / 1048576.0
        Log.i(
            DeviceFixtures.TAG,
            "cold SHA-256 over %.1f MiB took %d ms (%.1f MiB/s), %d marker(s) cleared first".format(
                mib, ms, mib / (ms / 1000.0), cleared,
            ),
        )

        // Not a timing gate, and specifically not usable as one: 460 ms / 2033 MiB/s
        // on this emulator is host-page-cache speed, not phone-storage speed. A real
        // first launch reads 183 MiB off UFS or eMMC cold, which is seconds. The
        // reason to record it at all is the warmup design question — verify on every
        // launch, or trust the marker after the first — and that question needs a
        // number from real hardware before it can be answered. Flagged for the
        // device checklist rather than settled here.
        assertTrue(ms > 0, "elapsed time did not advance — clock or harness problem")
    }

    @Test
    fun the_second_verification_is_served_from_markers() {
        for (spec in ModelCatalog.installTime) DeviceFixtures.requireModel(spec.id)
        DeviceFixtures.registry.verifyAll(ModelCatalog.installTime)

        val t0 = SystemClock.elapsedRealtime()
        DeviceFixtures.registry.verifyAll(ModelCatalog.installTime)
        val ms = SystemClock.elapsedRealtime() - t0
        Log.i(DeviceFixtures.TAG, "cached verifyAll took $ms ms")

        // The marker exists so that launch #2 does not re-hash the model set. If
        // it is not dramatically faster the memoisation is not working, whatever
        // the JVM unit test says about a 4 KiB temp file.
        assertTrue(ms < 2_000, "cached verifyAll took ${ms}ms — markers are not being honoured")
    }

    @Test
    fun the_catalog_is_exactly_the_on_device_识物_set() {
        // Cloud migration (v0.7): the Speaking track's models (whisper, VAD, MMS,
        // espeak) moved to the server, so the catalog must NOT grow them back and
        // they must NOT be delivered to the device — a stale push or a re-added
        // spec would silently re-inflate the APK the size optimisation just cut.
        assertEquals(2, ModelCatalog.all.size, "catalog drifted from the 2-model 识物 set")
        val names = ModelCatalog.all.map { it.fileName }
        assertEquals(
            setOf("w2v2_base_69_fp16.onnx", "yoloe-26s-pf.onnx"),
            names.toSet(),
        )
        // The four Speaking files, if any are present on the device, are dead
        // weight from a pre-migration push — flag rather than silently carry them.
        val stale = listOf(
            "mms_fa_int8_transformer.onnx",
            "espeak_cv_ft_int8.onnx",
            "silero_vad.onnx",
            "base.en-encoder.int8.onnx",
        ).filter { File(DeviceFixtures.modelDir, it).isFile }
        assertTrue(
            stale.isEmpty(),
            "pre-cloud Speaking models still pushed: ${stale.joinToString()}",
        )
    }
}
