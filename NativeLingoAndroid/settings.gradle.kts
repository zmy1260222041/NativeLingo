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

        // sherpa-onnx (:core-asr) is published only as a GitHub release asset —
        // k2-fsa has no Maven Central group, and the `sherpa-onnx` hits there are
        // third-party repackages. An ivy repo over the release URLs makes it a
        // real module dependency instead of a local .aar file, which matters:
        // AGP refuses to build a library AAR that has direct local .aar deps.
        // The download is pinned by sha256 in :core-asr (`verifySherpaAar`).
        ivy("https://github.com/k2-fsa/sherpa-onnx/releases/download") {
            patternLayout { artifact("v[revision]/[artifact]-[revision].[ext]") }
            metadataSources { artifact() }   // no POM/ivy.xml published
            content { includeGroup("com.k2fsa.sherpa.onnx") }
        }
    }
}

rootProject.name = "NativeLingo"

// Phase 1 (now): pure-JVM scoring core + golden-parity harness — Gate A/B/C truth.
include(":core-scoring")

// Phase 2: ONNX wav2vec2-base-960h (6-9 layers mean) SSL encoder.
include(":core-embed")

// Phase 2: MMS CTC forced alignment — word boundaries (FR-2) + replay spans (FR-8).
include(":core-align")

// Phase 2: sherpa-onnx Whisper transcription + Silero VAD (FR-2 reference text).
include(":core-asr")

// Phase 2: MediaExtractor/MediaCodec audio decode + :core-scoring resampling.
include(":core-audio")

// Where the ~891 MiB of int8 weights come from at runtime (NFR-4② asset pack).
// Landed ahead of its planned Phase-4 slot: the device-side gate harness cannot
// run without a way to locate models on a device, and "locate + verify" is the
// same problem for a pushed fixture directory and for a Play asset pack.
include(":core-models")

// Phase 4: application shell (Compose UI, repos, audio, warmup). Stub for now.
include(":app")

// Phased modules — added when their phase begins (docs/android-migration.md §8/§9):
//   Phase 3: :core-mdd
