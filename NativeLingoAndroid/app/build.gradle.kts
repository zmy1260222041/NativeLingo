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
