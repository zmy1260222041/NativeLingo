package com.nativelingo.app.repo

import android.content.Context
import android.util.Log
import com.google.android.play.core.assetpacks.AssetPackManager
import com.google.android.play.core.assetpacks.AssetPackManagerFactory
import com.nativelingo.models.ModelSpec
import com.nativelingo.models.ModelSource
import java.io.File

/**
 * A [ModelSource] backed by the install-time Play asset pack — the production
 * model-delivery path (NFR-4②). Install-time packs are unpacked at install into
 * an app-private directory [AssetPackManager.getPackLocation] exposes via
 * [assetsPath][com.google.android.play.core.assetpacks.AssetPackLocation.assetsPath];
 * because that is a real directory (not a deflated APK entry), ONNX/sherpa can
 * take its path arguments directly — no copy-out, no doubled footprint. This is
 * the property `core-models/.../ModelSource.kt` left as a deliberately-absent
 * Phase-4 seam.
 *
 * `getPackLocation` for an install-time pack returns a non-null location on the
 * very first launch (it installed with the app), so resolution is synchronous.
 *
 * **Verification caveat (M3):** under a plain `bundletool install-apks` local
 * install, Play services on the emulator can return a location whose
 * `assetsPath()` is null (the pack split is installed — visible as
 * `split_nlg_models.apk` — but not registered with the asset-delivery service).
 * That is a *testing-harness* limitation, not a packaging defect: a Play Store
 * install (or `bundletool --local-testing`) exposes the path. [locate] degrades
 * gracefully (returns null) so the registry falls through to the next source
 * rather than crashing.
 */
class AssetPackModelSource(
    context: Context,
    private val packName: String = PACK_NAME,
) : ModelSource {

    private val manager: AssetPackManager = AssetPackManagerFactory.getInstance(context.applicationContext)

    override val description: String = "install-time asset pack '$packName'"

    override fun locate(spec: ModelSpec): File? {
        val loc = manager.getPackLocation(packName)
        val path = loc?.assetsPath()
        if (path == null) {
            // Logged once-per-file is noisy but this is the diagnostic path; the
            // registry only calls locate when resolving, and a null path is the
            // one situation worth seeing in logcat during delivery bring-up.
            Log.w(TAG, "asset pack '$packName' not resolvable under local install: location=${loc != null}, assetsPath=null")
            return null
        }
        val file = File(path, spec.fileName)
        return if (file.isFile) file else null
    }

    companion object {
        /** Must match `assetPack.packName` in asset-pack-models/build.gradle.kts. */
        const val PACK_NAME = "nlg_models"
        private const val TAG = "NLAssetPack"
    }
}

