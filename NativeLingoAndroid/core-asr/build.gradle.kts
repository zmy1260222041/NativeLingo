// :core-asr — sherpa-onnx Whisper transcription (FR-2 reference text) and
// Silero VAD (speech spans for windowing; "is anyone talking" for FR-3).
//
// Deliberately thin. Everything about transcription that can be wrong in a way
// worth testing — where the audio is cut, how the text becomes practice units —
// lives in :core-scoring (`segment/AsrWindowPlanner.kt`, `SentenceSegmenter`),
// because cut positions decide practice-unit boundaries and must be verifiable
// on the JVM against the macOS golden. What is left here is JNI plumbing.
//
// See docs/reviews/2026-07-26-android-gate-f-asr-text.md (R-10 / Gate F).

// Imported rather than fully qualified: in a Kotlin build script `java` resolves
// to the JavaPluginExtension, so `java.security.MessageDigest` does not compile.
import java.security.MessageDigest

plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.android)
}

android {
    namespace = "com.nativelingo.asr"
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

/** Resolves the same AAR again, in isolation, so [verifySherpaAar] can hash it. */
val sherpaVerify: Configuration by configurations.creating { isTransitive = false }

dependencies {
    api(project(":core-scoring"))

    // Resolved through the ivy-over-GitHub-releases repo declared in
    // settings.gradle.kts. `artifact { type = "aar" }` is required because that
    // repo publishes no metadata, so Gradle has no way to know the packaging.
    //
    // **The static-link variant is chosen on purpose.** The default AAR ships its
    // own `libonnxruntime.so`, which collides with the one `onnxruntime-android`
    // brings for :core-embed/:core-align/:core-mdd. Both are 1.27.0 today, so the
    // collision would resolve harmlessly under `pickFirst` — and that is exactly
    // the problem: the day either side bumps, whichever .so wins silently serves
    // both, and the failure is a field crash rather than a build error. Static
    // linking removes the shared symbol. It costs ~19MB of duplicated ORT per
    // ABI, which is part of why :app ships arm64-v8a only (see there).
    implementation(libs.sherpa.onnx) { artifact { type = "aar" } }

    sherpaVerify(libs.sherpa.onnx) { artifact { type = "aar" } }

    testImplementation(kotlin("test"))
}

// --- pinned checksum ----------------------------------------------------------
//
// The ivy repo above is a plain HTTPS download with no signatures, so pin the
// bytes. Gradle's own dependency verification would be the idiomatic mechanism,
// but enabling it means enumerating checksums for every dependency in the build;
// this is the same guarantee for the one dependency that is not coming from a
// signed Maven repo.
val verifySherpaAar = tasks.register("verifySherpaAar") {
    description = "Fails the build if the sherpa-onnx AAR is not the bytes we measured Gate F with."
    val expected = "dc5ac19a28dee3bffc5e5a5d50cb6afa977703fc4a7ee535a308506990fdd295"
    val files = sherpaVerify.incoming.files
    inputs.files(files)
    inputs.property("sha256", expected)
    outputs.upToDateWhen { true }
    doLast {
        // A `for` over an empty resolution would pass silently, which is the one
        // way a checksum guard can be worse than none.
        if (files.files.size != 1) {
            throw GradleException("expected exactly one sherpa-onnx artifact, got ${files.files}")
        }
        for (f in files) {
            val got = MessageDigest.getInstance("SHA-256")
                .digest(f.readBytes()).joinToString("") { b -> "%02x".format(b) }
            if (got != expected) {
                throw GradleException(
                    "sherpa-onnx AAR checksum mismatch for ${f.name}\n" +
                        "  expected $expected\n  got      $got\n" +
                        "If the version was bumped on purpose, re-measure Gate F " +
                        "(scripts/asr_text_parity.py) before updating this pin."
                )
            }
        }
    }
}

tasks.named("preBuild") { dependsOn(verifySherpaAar) }
