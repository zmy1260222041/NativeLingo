package com.nativelingo.models

import java.io.File

/**
 * Somewhere model files can be found.
 *
 * Every source resolves to a real [File] on the filesystem, and that is a
 * constraint worth stating rather than discovering: ONNX Runtime's
 * `createSession(String)` and sherpa-onnx's `OfflineWhisperModelConfig` both
 * take paths. A model packed inside the APK's `assets/` is *not* a file — it is
 * a deflated entry in a zip — so bundling would mean copying ~891 MiB out to
 * internal storage on first launch, doubling the install footprint for the
 * duration of the copy. NFR-4② chose the install-time asset pack precisely
 * because Play delivers it as an already-unpacked directory (uncompressed,
 * `AssetPackLocation.assetsPath()`), which this interface can hand over
 * directly.
 */
interface ModelSource {
    /** Shown in "model missing" diagnostics, so it should say *where*, not *what*. */
    val description: String

    /** The file, or null if this source does not have it. Must not throw. */
    fun locate(spec: ModelSpec): File?
}

/**
 * A plain directory of flat files.
 *
 * Three callers, one implementation:
 *  - the Play install-time asset pack (`AssetPackLocation.assetsPath()`);
 *  - `adb push` fixtures under `getExternalFilesDir()`, which is how the
 *    device-side gate harness runs without Play at all;
 *  - a sideloaded/debug build pointed at internal storage.
 *
 * The asset-pack wiring itself (`AssetPackManager`, `com.google.android.play:
 * asset-delivery`) is Phase 4 and deliberately absent: it needs a Play Console
 * app entry to test end to end, and nothing about the gates depends on it. What
 * matters now is that the seam exists, so adding it is a new [ModelSource] and
 * not a change to every call site.
 */
class DirectoryModelSource(
    private val dir: File,
    override val description: String,
) : ModelSource {
    override fun locate(spec: ModelSpec): File? {
        val f = File(dir, spec.fileName)
        return if (f.isFile) f else null
    }

    override fun toString(): String = "$description ($dir)"
}
