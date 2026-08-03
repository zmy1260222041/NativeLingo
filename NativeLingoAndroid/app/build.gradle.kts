// :app — Phase 4 application shell: Compose UI, manual AppContainer DI,
// AudioRecord (FR-3), Media3 playback (FR-8), VideoRepository/RecordingsRepository,
// AnalyzePipeline, first-launch model verification/warmup.

import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}

// Release signing — reads keystore.properties next to this file (gitignored).
// CI can set the same keys via env: ORG_GRADLE_PROJECT_storeFile, etc.
val keystorePropsFile = rootProject.file("keystore.properties")
val keystoreProps = Properties().apply {
    if (keystorePropsFile.isFile) keystorePropsFile.inputStream().use { load(it) }
}
fun keystoreProp(name: String): String? =
    (project.findProperty(name) as? String) ?: keystoreProps.getProperty(name)

android {
    namespace = "com.nativelingo.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.nativelingo.app"
        minSdk = 28          // NFR-4①: Android 9+ / API 28+
        targetSdk = 35
        versionCode = 1
        versionName = "0.7.1"

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
        ndk { abiFilters += "arm64-v8a" }

        // Cloud Speaking backend (Duolingo-style server-side scoring). The
        // server URL is a build property; the AUTH token is deliberately NOT
        // here — the APK ships with no credential (OWASP M1): the app registers
        // per-device via POST /register with an operator-issued code (v0.7.1).
        //  -PNATIVELINGO_SERVER_URL=http://10.0.2.2:8756
        // The default URL points at the self-hosted production server.
        val serverUrl = (project.findProperty("NATIVELINGO_SERVER_URL") as? String)
            ?: "http://124.220.234.178:8756"
        buildConfigField("String", "SERVER_URL", "\"$serverUrl\"")
        // Test-only: a one-time registration code injected into the test APK
        // (expires in 24 h, burned on use) so the device-gate suite can
        // register without a UI. Always empty in release builds.
        val serverRegCode = (project.findProperty("NATIVELINGO_SERVER_REG_CODE") as? String)
            ?: ""
        buildConfigField("String", "SERVER_REG_CODE", "\"$serverRegCode\"")
    }

    signingConfigs {
        val storeFile = keystoreProp("storeFile")
        val storePassword = keystoreProp("storePassword")
        val keyAlias = keystoreProp("keyAlias")
        val keyPassword = keystoreProp("keyPassword")
        if (storeFile != null && storePassword != null && keyAlias != null && keyPassword != null) {
            create("release") {
                this.storeFile = rootProject.file(storeFile)
                this.storePassword = storePassword
                this.keyAlias = keyAlias
                this.keyPassword = keyPassword
            }
        }
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("release")
            isMinifyEnabled = false
        }
    }

    buildFeatures {
        compose = true
        // Cloud Speaking backend address/token are injected at build time.
        buildConfig = true
    }

    // Models ship inside the APK's assets/models/ for GitHub releases (extracted to
    // filesDir on first launch). For Play Store distribution, switch back to the
    // install-time asset pack: uncomment the line below and comment out syncModelsToAssets.
    // assetPacks += listOf(":asset-pack-models")

    // The curated corpus (7.1.mp4 + .sentences.json) is an uncompressed asset so
    // ExoPlayer's asset:/// scheme and MediaCodec get a clean file descriptor.
    androidResources {
        noCompress.add("mp4")
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

        // Drop every ABI but the one we ship — see the long note in defaultConfig.
        jniLibs.excludes += setOf("lib/x86/**", "lib/x86_64/**", "lib/armeabi-v7a/**")
    }
}

// Bundle the curated corpus from the repo's videos/ dir into the app's assets at
// build time. Not committed (the assets/corpus dir is gitignored): the source of
// truth is videos/ (shared with macOS); it is *synced* here so the APK is
// self-contained without duplicating 91 MiB in git. M3 moves this into the Play
// install-time asset pack alongside the models.
val corpusAssets = layout.projectDirectory.dir("src/main/assets/corpus")
val syncCorpus = tasks.register<Sync>("syncCorpus") {
    from(rootProject.layout.projectDirectory.dir("../videos")) {
        include("*.mp4", "*.sentences.json")
    }
    into(corpusAssets)
}
// Stage model weights into the APK's assets/models/ so AssetsModelSource can
// extract them to filesDir on first launch. Cloud migration (v0.7) cut the list
// from 7 files (935 MiB) to 2 (183 MiB): whisper/VAD/MMS/espeak moved to the
// server; only the 识物 stack ships — the SSL encoder (FR-17 pronunciation) and
// YOLOE (FR-13 detection).
// For Play Store distribution comment this block and uncomment assetPacks above.
val modelAssets = layout.projectDirectory.dir("src/main/assets/models")
val syncModelsToAssets = tasks.register<Sync>("syncModelsToAssets") {
    // Keep this list in lockstep with ModelCatalog.installTime + asset-pack-models/build.gradle.kts.
    from(rootProject.layout.projectDirectory.dir("../build/onnx").asFile.absolutePath) {
        include(
            "w2v2_base_69_fp16.onnx",
        )
    }
    // FR-13 (识物) — YOLOE-26S-PF. Sourced from models/yoloe-26s-pf/ (an Ultralytics
    // export, gitignored like the other large weights) rather than build/onnx/.
    from(rootProject.layout.projectDirectory.dir("../models/yoloe-26s-pf")) {
        include("yoloe-26s-pf.onnx")
    }
    into(modelAssets)
}

// FR-17 (识物 跟读) — pre-rendered Piper reference clips (Option D). Runtime TTS
// is blocked by sherpa-onnx OfflineTts's reuse crash (issue #3675 class), so the
// curated label vocabulary is rendered once offline (scripts/render_pronounce_refs.py)
// and shipped as 16 kHz mono PCM16 wavs. Sourced from models/pronounce-refs/.
val pronounceRefAssets = layout.projectDirectory.dir("src/main/assets/models/pronounce-refs")
val syncPronounceRefs = tasks.register<Sync>("syncPronounceRefs") {
    from(rootProject.layout.projectDirectory.dir("../models/pronounce-refs"))
    into(pronounceRefAssets)
}
tasks.matching { it.name.startsWith("merge") && it.name.endsWith("Assets") }
    .configureEach { dependsOn(syncPronounceRefs) }
tasks.matching {
    val n = it.name
    n.startsWith("generate") && n.contains("Lint") || n.startsWith("lint")
}.configureEach { dependsOn(syncPronounceRefs) }

// mergeAssets runs before packaging; making it depend on both syncs covers
// debug and release variants without touching the incubating applicationVariants API.
tasks.matching { it.name.startsWith("merge") && it.name.endsWith("Assets") }
    .configureEach { dependsOn(syncCorpus, syncModelsToAssets) }

// Lint tasks read assets and need the syncs to have run first.
tasks.matching {
    val n = it.name
    n.startsWith("generate") && n.contains("Lint") || n.startsWith("lint")
}.configureEach { dependsOn(syncModelsToAssets, syncCorpus) }

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.kotlinx.coroutines.android)

    // Compose (versions via the BOM).
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    debugImplementation(libs.androidx.compose.ui.tooling)

    // Media3 — muted-video playback (FR-3) and WAV-clip replay (FR-8).
    implementation(libs.androidx.media3.exoplayer)
    implementation(libs.androidx.media3.ui)

    // M3: install-time asset pack (NFR-4②). AssetPackManager resolves the pack's
    // unpacked directory; install-time packs are present immediately at first launch.
    implementation(libs.google.play.asset.delivery)

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
    implementation(project(":core-audio"))
    implementation(project(":core-models"))
    implementation(project(":core-vision"))
    implementation(libs.onnxruntime.android)

    // Cloud Speaking backend — OkHttp multipart uploads (video import, learner take).
    implementation(libs.okhttp)

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
