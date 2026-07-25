// :core-embed — ONNX wav2vec2-base-960h (layers 6-9 mean) SSL encoder.
//
// Production runs on onnxruntime-android (arm64-v8a native). The SAME
// ai.onnxruntime.* API is unit-tested on the JVM with the macOS-native
// onnxruntime (desktop) package — no emulator needed to verify inference
// parity (device-side R-5 on JVM). See docs/android-migration.md §8/§10.
plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.android)
}

android {
    namespace = "com.nativelingo.embed"
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
    implementation(project(":core-scoring"))
    implementation(libs.onnxruntime.android)

    testImplementation(libs.onnxruntime.desktop)
    testImplementation(kotlin("test"))
}
