// :core-models — where the ~891 MiB of int8 weights come from at runtime.
//
// It answers exactly one question for every other module: "give me the file for
// model X." Nothing here loads a model or runs inference; :core-embed,
// :core-align, :core-asr and (Phase 3) :core-mdd take a path.
//
// The reason it is its own module rather than a few lines in :app is NFR-4②:
// the models do not ship inside the APK. whisper base.en int8 alone is 152 MiB,
// past Play's base-APK ceiling, and the other three are 737 MiB, so all four
// arrive via an install-time asset pack. That means "where is this file" has
// several answers depending on build flavour and test harness, and the answer
// has to be verifiable — a truncated 338 MiB download does not throw, it
// produces wrong scores. Hence [ModelRegistry] with a checksum gate.
//
// See docs/PRD.md NFR-4②, docs/reviews/2026-07-26-android-r11-whisper-tier.md.
plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.android)
}

android {
    namespace = "com.nativelingo.models"
    compileSdk = 35

    defaultConfig { minSdk = 28 }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlin { jvmToolchain(17) }

    testOptions {
        unitTests.isReturnDefaultValues = true
        unitTests.all { it.useJUnitPlatform() }
    }
}

dependencies {
    testImplementation(kotlin("test"))
}
