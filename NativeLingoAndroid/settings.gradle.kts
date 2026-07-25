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

// Phase 2: MMS CTC forced alignment — word boundaries (FR-2) + replay spans (FR-8).
include(":core-align")

// Phase 4: application shell (Compose UI, repos, audio, warmup). Stub for now.
include(":app")

// Phased modules — added when their phase begins (docs/android-migration.md §8/§9):
//   Phase 2: :core-asr, :core-audio
//   Phase 3: :core-mdd
//   Phase 4: :core-models
