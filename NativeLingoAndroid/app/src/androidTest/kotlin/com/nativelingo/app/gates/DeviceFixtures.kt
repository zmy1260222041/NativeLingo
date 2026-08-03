package com.nativelingo.app.gates

import android.content.Context
import android.util.Log
import androidx.test.platform.app.InstrumentationRegistry
import com.nativelingo.models.DirectoryModelSource
import com.nativelingo.models.ModelCatalog
import com.nativelingo.models.ModelId
import com.nativelingo.models.ModelRegistry
import com.nativelingo.scoring.TestJson
import com.nativelingo.scoring.io.NpyReader
import com.nativelingo.scoring.io.frames2d
import java.io.File

/**
 * Shared plumbing for the device-side gate suite.
 *
 * Two distinct asset spaces, and mixing them up is the first thing that goes
 * wrong here: the macOS golden fixtures live in the **test** APK's assets (see
 * `app/build.gradle.kts`, which mounts `core-scoring/src/test/resources/golden`
 * there), while `getExternalFilesDir` belongs to the **app under test**. So
 * goldens come from `InstrumentationRegistry.getInstrumentation().context` and
 * model files from `.targetContext`.
 *
 * Models are not in either APK — they are ~183 MiB (the 识物 set only, since the
 * v0.7 cloud migration) and arrive via an asset pack in production (NFR-4②).
 * For the harness they are delivered by:
 *
 * ```
 * scripts/run_device_gates.sh      # installs, delivers models, instruments
 * ```
 */
object DeviceFixtures {

    const val TAG = "NLGates"

    /** The app under test — owns the pushed model directory. */
    val appContext: Context get() = InstrumentationRegistry.getInstrumentation().targetContext

    /** The test APK — owns the golden assets. */
    private val testContext: Context get() = InstrumentationRegistry.getInstrumentation().context

    /**
     * Where `push_device_models.sh` puts the weights: app-private internal
     * storage, `/data/data/<pkg>/files/models`.
     *
     * Not `getExternalFilesDir`. That was the first choice and it fails silently:
     * on API 30+ `/sdcard/Android/data/<pkg>` is a FUSE view, `adb push` writes it
     * through the shell namespace, and the app cannot read files that land there
     * owned by uid `shell` — `adb shell ls` shows all seven at full length while
     * the app sees an empty directory. Internal storage is also the closer
     * analogue of production, where an install-time asset pack is unpacked into
     * app-private space, not onto shared storage.
     */
    val modelDir: File get() = File(appContext.filesDir, "models")

    /** Checksum markers: deliberately NOT next to the models. */
    val stateDir: File get() = File(appContext.filesDir, "model-state")

    val registry: ModelRegistry by lazy {
        ModelRegistry(listOf(DirectoryModelSource(modelDir, "推送的模型目录")), stateDir)
    }

    // --- golden assets ---------------------------------------------------------

    fun assetText(path: String): String =
        testContext.assets.open(path).use { it.readBytes().decodeToString() }

    fun assetJson(path: String): Map<String, Any?> = TestJson.obj(assetText(path))

    private fun npy(path: String) = testContext.assets.open(path).use { NpyReader.read(it) }

    /** A 1-D float golden (waveform, normalized input, reference decode). */
    fun float1d(path: String): FloatArray {
        val a = npy(path)
        return FloatArray(a.size) { a.data[it].toFloat() }
    }

    /** A 2-D golden (embeddings, emissions). */
    fun frames(path: String): Array<FloatArray> = npy(path).frames2d()

    /**
     * Copy an asset out to cache and return the file.
     *
     * `MediaExtractor.setDataSource` needs a path or a file descriptor with a real
     * offset/length; an `AssetFileDescriptor` from a *compressed* asset entry has
     * neither. Rather than fight the packaging rules, the container fixtures are
     * simply materialised — they are ~40 KB each.
     */
    fun assetToCache(path: String): File {
        val out = File(appContext.cacheDir, path.substringAfterLast('/'))
        if (!out.isFile || out.length() == 0L) {
            testContext.assets.open(path).use { ins -> out.outputStream().use { ins.copyTo(it) } }
        }
        return out
    }

    // --- models ----------------------------------------------------------------

    /**
     * Resolve a model or fail with what to do about it.
     *
     * Deliberately a hard failure, not `Assume.assumeTrue`. The entire purpose of
     * this suite is that it ran against real weights on real hardware; a suite
     * that skips itself into a green tick when the models are absent is worse than
     * no suite, because the gate record would cite it.
     */
    fun requireModel(id: ModelId): File = try {
        registry.resolve(id)
    } catch (e: Exception) {
        throw AssertionError(
            "${e.message}\n" +
                "模型未就绪。在主机上运行:scripts/run_device_gates.sh\n" +
                "目标目录:$modelDir",
            e,
        )
    }

    fun logPresentModels() {
        val present = ModelCatalog.all.count { spec ->
            File(modelDir, spec.fileName).let { it.isFile && it.length() == spec.bytes } }
        Log.i(TAG, "models present at full length: $present/${ModelCatalog.all.size} in $modelDir")
    }
}
