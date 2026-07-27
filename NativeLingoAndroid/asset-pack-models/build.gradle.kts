// :asset-pack-models — the install-time Play asset pack (NFR-4②). The 935 MiB
// of model weights that do not fit in the 150 MiB base APK ship here and are
// unpacked at install to a directory the app reads straight from (no copy-out —
// see core-models/.../ModelSource.kt). The model files are *synced* into
// src/main/assets from the host at build time (syncModels below) and the assets
// dir is gitignored: 935 MiB is not source, and its sources (build/onnx exports,
// /tmp/sherpa-models) are rebuildable.
plugins {
    // Part of AGP (ships with com.android.application) — apply by id without a
    // version; the catalog alias pins 8.7.3 and conflicts ("already on the
    // classpath with an unknown version").
    id("com.android.asset-pack")
}

assetPack {
    packName.set("nlg_models")
    dynamicDelivery {
        deliveryType.set("install-time")
    }
}

// Stage the install-time set (7 files, 935 MiB) — the same list
// scripts/push_device_models.sh pushes, sourced from the same host dirs. Paths
// are resolved to plain strings (not closures over `rootProject`) so the task
// survives configuration cache (gradle.properties has it on).
val onnxDir = rootProject.layout.projectDirectory.dir("../build/onnx").asFile.absolutePath
val sherpaDir = providers.gradleProperty("sherpaModelsDir")
    .orElse(providers.environmentVariable("SHERPA_MODELS").orElse("/tmp/sherpa-models"))
    .get()
val modelAssets = layout.projectDirectory.dir("src/main/assets")

val syncModels = tasks.register<Sync>("syncModels") {
    // Keep this list in lockstep with ModelCatalog.installTime + push_device_models.sh.
    from(onnxDir) {
        include(
            "w2v2_base_69_fp16.onnx",        // SSL encoder (R-5, fp16 after R-12)
            "mms_fa_int8_transformer.onnx",  // forced aligner (R-6)
            "espeak_cv_ft_int8.onnx",        // phoneme MDD (R-7) — included for completeness
        )
    }
    from(sherpaDir) {
        include(
            "silero_vad.onnx",
            "sherpa-onnx-whisper-base.en/base.en-encoder.int8.onnx",
            "sherpa-onnx-whisper-base.en/base.en-decoder.int8.onnx",
            "sherpa-onnx-whisper-base.en/base.en-tokens.txt",
        )
        // flatten the whisper subdir so the pack is flat (ModelCatalog uses bare fileNames)
        eachFile { path = name }
    }
    into(modelAssets)
}

// :app's PreBundleTask reads this module's assets; order it after staging.
// (Matching is lazy, so it catches the debug/release variants as they register.)
tasks.matching { it.name.endsWith("PreBundleTask") || (it.name.startsWith("merge") && it.name.endsWith("Assets")) }
    .configureEach { dependsOn(syncModels) }
