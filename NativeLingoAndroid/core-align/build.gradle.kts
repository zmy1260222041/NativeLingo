// :core-align — MMS CTC forced alignment (FR-2 word boundaries, FR-8 replay spans).
//
// The emission model is the HF-re-hosted MMS_FA export (int8 transformer-only,
// 338MB; scripts/onnx_export_mms.py, R-6). The Viterbi itself lives in
// :core-scoring so it stays pure-JVM and is shared with :core-mdd (Phase 3).
plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.android)
}

android {
    namespace = "com.nativelingo.align"
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
    implementation(libs.onnxruntime.android)

    testImplementation(libs.onnxruntime.desktop)
    testImplementation(testFixtures(project(":core-scoring")))
    testImplementation(kotlin("test"))
}
