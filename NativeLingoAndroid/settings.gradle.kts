pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "NativeLingo"

// Phase 1 (now): pure-JVM scoring core + golden-parity harness — Gate A/B/C truth.
include(":core-scoring")

// Phase 2: ONNX wav2vec2-base-960h (6-9 layers mean) SSL encoder.
include(":core-embed")

// Memorizing (识物) module — YOLOE-26S-PF macro object detection (FR-13).
// A Kotlin port of desktop/backend/core/vision.py on onnxruntime-android; the
// same curated label table and 640px + overlapping 1280px tile pipeline.
include(":core-vision")

// Phase 2: MediaExtractor/MediaCodec audio decode + :core-scoring resampling.
include(":core-audio")

// Where the model weights come from at runtime (NFR-4② asset pack).
// Landed ahead of its planned Phase-4 slot: the device-side gate harness cannot
// run without a way to locate models on a device, and "locate + verify" is the
// same problem for a pushed fixture directory and for a Play asset pack.
include(":core-models")

// Phase 4: application shell (Compose UI, repos, audio, warmup). Stub for now.
include(":app")

// v0.7 cloud migration removed the Speaking track's on-device modules
// (`:core-align` MMS + `:core-asr` whisper/VAD — transcription, alignment and
// phoneme diagnosis now run server-side). The sherpa-onnx ivy repo was their
// dependency and is gone with them.

// Phase 4 / M3: the install-time asset pack (NFR-4②). Delivered by Play
// at install, unpacked to an app-private directory `AssetPackLocation.assetsPath()`
// points at — which is why a model can be a File for ONNX path args without
// a copy-out (see core-models/.../ModelSource.kt).
//
// COMMENTED OUT for GitHub APK releases: models are bundled in :app's assets/models/
// instead and extracted on first launch by AssetsModelSource. To switch back to
// Play distribution, uncomment this line and the assetPacks block in app/build.gradle.kts.
// include(":asset-pack-models")

// Phased modules — added when their phase begins (docs/android-migration.md §8/§9):
//   Phase 3: :core-mdd
