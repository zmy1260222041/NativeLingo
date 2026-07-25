// :core-audio — decoding a video's audio track to the 16 kHz mono float32 the
// pipeline expects (`backend/core/video.py:extract_audio` on macOS).
//
// Thin, like :core-asr, and for the same reason. Everything numeric lives in
// :core-scoring: resampling in `resample/PolyphaseResampler.kt` (it feeds a
// calibrated score), peak normalisation and silence trimming in
// `audio/AudioPreproc.kt`, WAV I/O in `io/WavIo.kt`. What is left here is
// MediaExtractor/MediaCodec plumbing against the platform.
//
// No NDK, no FFmpeg, no bundled .so — see R-9,
// docs/reviews/2026-07-26-android-gate-e-audio-decode.md, which reversed the
// original plan's FFmpeg-source-build route after measuring that the choice of
// resampler moves a score by 0.00.
plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.android)
}

android {
    namespace = "com.nativelingo.audio"
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
    api(project(":core-scoring"))
    testImplementation(kotlin("test"))
}
