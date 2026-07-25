// :app — Phase 4 application shell (Compose UI, ViewModel/DI, AudioRecord,
// Media3 playback, VideoRepository/RecordingsRepository, first-launch model
// download + warmup, FR-12 Room history). STUB for now: just enough to be a
// valid `com.android.application` module. UI/repos/audio land in Phase 4.
plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
}

android {
    namespace = "com.nativelingo.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.nativelingo.app"
        minSdk = 28          // NFR-4①: Android 9+ / API 28+
        targetSdk = 35
        versionCode = 1
        versionName = "0.5.0"

        // 64-bit only. Not a size optimisation first — a correctness one: Gate D
        // budgets ~3.5GB peak RSS (espeak int8 alone is 302.9MB of weights plus
        // ORT arenas), which a 32-bit process cannot address. Any device that can
        // run this app is arm64. It also halves the native payload, which matters
        // because :core-asr statically links its own copy of ONNX Runtime
        // (~19MB/ABI) to avoid a silent .so collision — see core-asr/build.gradle.kts.
        //
        // Revisit if the model set ever shrinks enough for armeabi-v7a to be
        // viable; that is a device-support change and belongs in the PRD.
        ndk { abiFilters += "arm64-v8a" }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlin {
        jvmToolchain(17)
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
}
