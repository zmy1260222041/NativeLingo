// :core-scoring — pure-JVM scoring core.
//
// HARD INVARIANT: this module has ZERO Android dependencies (only the Kotlin
// stdlib). It must stay buildable/testable on plain JVM CI so the macOS golden
// fixtures (src/test/resources/golden) drive numerical-parity tests without a
// device or emulator. See docs/android-migration.md §8 (module invariant) and
// §10 (verification layers).
//
// Phase-1 lands here: DTW (align), CMVN (speaker_norm), calibrated scoring
// (score_b), detail projection, word_diff, feedback, and the shared CTC
// Viterbi (CtcViterbi.kt) used by both forced alignment and phoneme MDD.
plugins {
    alias(libs.plugins.kotlin.jvm)
}

java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}

kotlin {
    jvmToolchain(17)
}

dependencies {
    testImplementation(kotlin("test"))
}

tasks.test {
    useJUnitPlatform()
}
