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

// Phase 4: application shell (Compose UI, repos, audio, warmup). Stub for now.
include(":app")

// Phased modules — added when their phase begins (docs/android-migration.md §8/§9):
//   Phase 2: :core-embed, :core-asr, :core-audio, :core-align
//   Phase 3: :core-mdd
//   Phase 4: :core-models
