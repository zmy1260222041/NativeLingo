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

        // The device-side gate harness lives in this module's androidTest source
        // set (src/androidTest) rather than in each core module's, for one reason:
        // Gate D (NFR-4③, peak RSS <3.5GB) is a property of ONE process holding
        // the SSL encoder, the aligner, whisper and espeak at once. Four separate
        // test APKs each measure a different, smaller thing.
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

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

    sourceSets {
        // The macOS golden fixtures, mounted straight into the test APK's assets
        // instead of being copied or pushed. 7.4MB, and the alternative — a second
        // copy under app/src/androidTest/assets — is how the device numbers and the
        // JVM numbers would start being measured against different baselines.
        getByName("androidTest") {
            assets.srcDirs("../core-scoring/src/test/resources/golden")
        }
    }

    packaging {
        // Both onnxruntime-android and the sherpa-onnx static-link AAR carry
        // headers/licence files under META-INF; nothing here depends on which one
        // wins.
        resources.excludes += setOf("META-INF/**")

        // Drop every ABI but the one we ship. `ndk.abiFilters` above is not enough:
        // AGP does not apply it to the androidTest variant's native-lib merge, so
        // the merge sees all four slices of both AARs.
        //
        // And in one of those slices they genuinely collide. The sherpa-onnx AAR is
        // named `sherpa-onnx-static-link-onnxruntime`, but the static linking only
        // holds for arm64-v8a, armeabi-v7a and x86_64 — its **x86** slice ships a
        // separate `libonnxruntime.so` (25.9MB) alongside the JNI lib, which is a
        // second copy of the library `onnxruntime-android` already provides
        // (34.0MB, a different version: 1.13.4 vs 1.27.0). Two `libonnxruntime.so`
        // at the same path is an error the build refuses to guess at, and rightly:
        // `pickFirst` would resolve it by loading whichever ORT won the race for a
        // library the other module was compiled against.
        //
        // So this is not a workaround for a packaging quirk — it is NFR-4①'s
        // arm64-only decision being what actually makes the two runtimes able to
        // share a process. If armeabi-v7a is ever revisited, check the x86 slice
        // first; the collision is real, just not on any ABI we build for.
        jniLibs.excludes += setOf("lib/x86/**", "lib/x86_64/**", "lib/armeabi-v7a/**")
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)

    // The cores belong to the *app*, not to the test APK, even though today only
    // the harness calls them.
    //
    // They started out `androidTestImplementation`, on the reasoning that :app is
    // a Phase-4 stub and shouldn't claim dependencies it doesn't use yet. That is
    // not a choice AGP lets you make: a native library packaged in the test APK is
    // not on the app process's `dlopen` search path, so every ONNX and sherpa test
    // died at class-init with `library "libonnxruntime4j_jni.so" not found` while
    // `unzip -l` showed all three .so present — in the wrong APK. Instrumentation
    // merges the test APK's *dex* into the app's classloader; its `lib/` is not
    // merged the same way.
    //
    // It is also the arrangement Gate D (NFR-4③) is actually about: peak RSS of
    // one process holding all sessions is a property of the app process, so the
    // sessions must be loaded the way the app will load them.
    implementation(project(":core-scoring"))
    implementation(project(":core-embed"))
    implementation(project(":core-align"))
    implementation(project(":core-asr"))
    implementation(project(":core-audio"))
    implementation(project(":core-models"))
    implementation(libs.onnxruntime.android)

    // Test-only: golden-fixture helpers and the runner.
    androidTestImplementation(testFixtures(project(":core-scoring")))
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.androidx.test.junit)
    androidTestImplementation(libs.junit)
    // kotlin.test's assertions, so the gate tests read the same as the JVM ones
    // they re-check. Resolves to kotlin-test-junit here because JUnit 4 is on the
    // classpath, so `assertNotNull`'s smart-cast contract works as it does on the JVM.
    androidTestImplementation(kotlin("test"))
}
