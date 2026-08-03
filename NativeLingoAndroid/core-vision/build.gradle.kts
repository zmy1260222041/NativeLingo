// :core-vision — YOLOE-26S-PF macro object detection for the Memorizing module (FR-13).
//
// A faithful Kotlin port of desktop/backend/core/vision.py: the same prompt-free
// YOLOE ONNX export (detection-only), the same curated label table, the same
// 640px whole-image + overlapping 1280px tile pipeline and global NMS. Runs on
// onnxruntime-android in production; the JVM unit tests use the macOS-native
// onnxruntime (desktop) package so inference parity is verifiable without an
// emulator — the same split :core-embed uses.
plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.android)
}

android {
    namespace = "com.nativelingo.vision"
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
    implementation(libs.onnxruntime.android)
    // EXIF orientation reading for the canonical image contract (memorize-image-v1).
    implementation(libs.androidx.exifinterface)

    testImplementation(libs.onnxruntime.desktop)
    testImplementation(kotlin("test"))
}
