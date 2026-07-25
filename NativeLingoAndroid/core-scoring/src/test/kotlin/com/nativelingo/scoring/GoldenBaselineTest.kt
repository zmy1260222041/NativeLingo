package com.nativelingo.scoring

import com.nativelingo.scoring.io.NpyReader
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Seed of the Layer-1/2 parity harness (docs/android-migration.md §10).
 *
 * These tests prove the macOS golden fixtures (committed under
 * `src/test/resources/golden`, produced by `scripts/capture_golden.py`) are on
 * the classpath and parse correctly. The actual numerical-parity assertions
 * (DTW cost ±0.02, embedding cosine ≥0.995, speaker-invariance cost ≤0.18 …)
 * land in Phase 1 alongside the algorithm ports, which transform these fixtures
 * the same way the macOS backend does.
 *
 * Run: `./gradlew :core-scoring:test` (needs JDK 17 + the gradle wrapper).
 */
class GoldenBaselineTest {

    private fun golden(path: String): java.io.InputStream =
        javaClass.getResourceAsStream("/golden/$path")
            ?: error("missing golden resource: /golden/$path — run scripts/capture_golden.py")

    @Test
    fun manifest_is_present_and_describes_corpus() {
        val manifest = golden("manifest.json").bufferedReader().use { it.readText() }
        assertTrue(manifest.contains("speakervariance"), "manifest must list the speaker-invariance pair")
        assertTrue(manifest.contains("tolerances"), "manifest must declare parity tolerances")
    }

    @Test
    fun wav2vec2_embedding_fixture_parses() {
        // Gate A · Layer 2: macOS wav2vec2-base-960h layers 6-9 mean, (T, 768).
        val arr = NpyReader.read(golden("emb/ref_samantha.npy"))
        assertEquals(listOf(124, 768), arr.shape.toList())
        assertEquals(124 * 768, arr.data.size)
        assertEquals('f', arr.dtype)
        assertEquals(4, arr.dtypeBytes)
    }

    @Test
    fun dtw_path_fixture_parses() {
        // Gate A · Layer 1: banded-DTW path (K, 2), int64.
        val arr = NpyReader.read(golden("pair/speakervariance_path.npy"))
        assertEquals(2, arr.rank())
        assertEquals(2, arr.shape[1])
    }

    @Test
    fun mms_emission_fixture_parses() {
        // Gate B · Layer 2: MMS CTC emission (T, V), float32.
        val arr = NpyReader.read(golden("mms/ref_samantha_emission.npy"))
        assertEquals(2, arr.rank())
        assertEquals('f', arr.dtype)
    }
}
