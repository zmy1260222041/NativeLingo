package com.nativelingo.app.repo

import android.content.Context
import android.util.Log
import com.nativelingo.models.ModelCatalog
import com.nativelingo.models.ModelSource
import com.nativelingo.models.ModelSpec
import java.io.File
import java.io.FileOutputStream

/**
 * Extracts model files bundled in `assets/models/` to [targetDir] on first launch,
 * then resolves them as a plain directory thereafter.
 *
 * This replaces the Play install-time asset pack for GitHub APK releases: the
 * 935 MiB of weights are compressed inside the APK's assets and extracted once
 * to app-private storage. The copy is idempotent — a file at the right length
 * is assumed complete (a full SHA-256 check is the Warmup's job afterward).
 *
 * After extraction the models are plain files ONNX/sherpa can open directly,
 * same as [DirectoryModelSource]. The doubled footprint lasts only during the
 * first-run copy (after which the APK's compressed copy is never read again).
 *
 * **Why not keep models in assets and read them there?** ONNX Runtime's
 * `createSession(String)` and sherpa-onnx's model configs take file paths, not
 * file descriptors. An asset inside an APK is a deflated zip entry, not a file
 * the OS can open.
 */
class AssetsModelSource(
    context: Context,
    private val targetDir: File,
) : ModelSource {

    private val appContext: Context = context.applicationContext
    private val assetRoot = "models"

    /** The list of model files declared in the asset directory (may be empty if
     * the assets weren't staged — e.g. a dev build without the sync task). */
    val availableAssets: Array<String>
        get() = runCatching { appContext.assets.list(assetRoot) ?: emptyArray() }
            .getOrDefault(emptyArray())

    override val description: String = "APK assets/$assetRoot/ → ${targetDir.absolutePath}"

    // ── bulk extraction with progress ──────────────────────────────────────

    /**
     * Total bytes of models that are in assets but not yet at [targetDir] at the
     * correct length. Zero when everything is extracted.
     */
    fun pendingBytes(): Long {
        val assetFiles = availableAssets.toSet()
        if (assetFiles.isEmpty()) return 0L
        return ModelCatalog.installTime
            .filter { it.fileName in assetFiles }
            .sumOf { spec ->
                val target = File(targetDir, spec.fileName)
                if (target.isFile && target.length() == spec.bytes) 0L else spec.bytes
            }
    }

    /**
     * Copy every model file from assets to [targetDir] if not already present at
     * the right length. Reports [onProgress] with byte granularity so a progress
     * bar can show "extracting 935 MiB" as a determinate step before verification.
     *
     * Idempotent: files already at the correct length are skipped. A file at the
     * wrong length (crashed previous copy) is re-extracted.
     */
    fun extractAll(onProgress: (doneBytes: Long, totalBytes: Long) -> Unit) {
        targetDir.mkdirs()
        val assetFiles = availableAssets.toSet()
        if (assetFiles.isEmpty()) {
            Log.w(TAG, "no model files in assets/$assetRoot/ — was syncModelsToAssets run?")
            return
        }

        val toExtract = ModelCatalog.installTime.filter { it.fileName in assetFiles }
        if (toExtract.isEmpty()) return

        val total = toExtract.sumOf { it.bytes }
        var done = 0L

        for (spec in toExtract) {
            val target = File(targetDir, spec.fileName)
            if (target.isFile && target.length() == spec.bytes) {
                done += spec.bytes
                onProgress(done, total)
                continue
            }
            // Delete partial file from a previous crashed copy.
            target.delete()
            copyAsset("$assetRoot/${spec.fileName}", target)
            done += spec.bytes
            onProgress(done, total)
        }
    }

    // ── ModelSource ────────────────────────────────────────────────────────

    /**
     * Returns the file at [targetDir], copying it from assets first if absent.
     * Returns null when the file is not in assets either (lets the registry fall
     * through to the next source).
     */
    override fun locate(spec: ModelSpec): File? {
        val target = File(targetDir, spec.fileName)
        if (target.isFile && target.length() == spec.bytes) {
            return target
        }
        // Try a lazy single-file copy — covers the case where Warmup hasn't run
        // extractAll() yet (e.g. a model is resolved before the UI shows).
        val assetPath = "$assetRoot/${spec.fileName}"
        return copyAsset(assetPath, target, spec)
    }

    // ── internals ──────────────────────────────────────────────────────────

    /** Copy one file from assets to [dest]. Returns [dest] on success, null if
     * the asset doesn't exist or the copy fails. */
    private fun copyAsset(assetPath: String, dest: File, spec: ModelSpec? = null): File? {
        return try {
            dest.parentFile?.mkdirs()
            appContext.assets.open(assetPath).use { input ->
                FileOutputStream(dest).use { output ->
                    val buf = ByteArray(1 shl 20)  // 1 MiB
                    while (true) {
                        val n = input.read(buf)
                        if (n <= 0) break
                        output.write(buf, 0, n)
                    }
                }
            }
            // Verify length after copy — a short file means the asset was truncated
            // at build time, and we should not hand it to ONNX.
            val len = dest.length()
            if (spec != null && len != spec.bytes) {
                dest.delete()
                Log.w(TAG, "copied ${spec.fileName} is $len B, expected ${spec.bytes} — deleted")
                return null
            }
            Log.d(TAG, "extracted $assetPath → ${dest.absolutePath} ($len B)")
            dest
        } catch (e: Exception) {
            Log.w(TAG, "failed to extract $assetPath: ${e.message}")
            dest.delete()
            null
        }
    }

    companion object {
        private const val TAG = "NLAssetsSource"
    }
}
