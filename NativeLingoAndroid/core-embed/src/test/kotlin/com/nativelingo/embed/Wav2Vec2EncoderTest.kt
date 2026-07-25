package com.nativelingo.embed

import com.nativelingo.scoring.align.dtwAlign
import com.nativelingo.scoring.io.NpyReader
import com.nativelingo.scoring.io.frames2d
import com.nativelingo.scoring.norm.cmvn
import kotlin.math.abs
import kotlin.math.sqrt
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Device-side R-5 on JVM: the int8-transformer ONNX encoder (via onnxruntime's
 * Java API) reproduces the macOS golden embeddings within functional tolerance.
 *
 * Two independent checks:
 *  1. onnx_run_matches_golden — feed the golden NORMALIZED input → ONNX →
 *     compare to the macOS PyTorch embedding. Isolates the ONNX run.
 *  2. kotlin_normalization_matches_extractor — my Kotlin normalization matches
 *     the Wav2Vec2FeatureExtractor output element-wise.
 *
 * Loads the 95MB model from build/onnx (gitignored, regenerable via
 * scripts/onnx_export_spike.py); skips if absent.
 */
class Wav2Vec2EncoderTest {

    private val goldenDir = "../core-scoring/src/test/resources/golden"
    private val modelPath = "../../build/onnx/w2v2_base_69_int8_transformer.onnx"

    private fun npy(path: String) = NpyReader.read(java.io.File("$goldenDir/$path").inputStream())
    private fun emb(name: String) = npy("emb/$name.npy").frames2d()
    private fun float1d(path: String): FloatArray {
        val a = npy(path); return FloatArray(a.size) { a.data[it].toFloat() }
    }

    @Test
    fun kotlin_normalization_matches_extractor() {
        // runs without the model — verifies the normalization port standalone.
        for (name in listOf("ref_samantha", "crossvoice_daniel", "wrongtext_samantha")) {
            val mine = normalizeWav2Vec2(float1d("wav/$name.npy"))
            val gold = float1d("wav/${name}_input.npy")
            assertEquals(gold.size, mine.size, "$name length mismatch")
            var maxDiff = 0.0
            for (i in mine.indices) maxDiff = maxOf(maxDiff, abs(mine[i].toDouble() - gold[i].toDouble()))
            assertTrue(maxDiff < 1e-5, "$name normalization max-diff $maxDiff (need < 1e-5)")
        }
    }

    @Test
    fun onnx_run_matches_golden_embeddings() {
        val model = java.io.File(modelPath)
        if (!model.exists()) {
            println("SKIP: model not at $modelPath — run scripts/onnx_export_spike.py")
            return
        }
        Wav2Vec2Encoder(model.absolutePath).use { enc ->
            for (name in listOf("ref_samantha", "crossvoice_daniel", "wrongtext_samantha", "slow_samantha")) {
                // feed the golden normalized input → isolates the ONNX run
                val out = enc.runNormalized(float1d("wav/${name}_input.npy"))
                val cos = cosAfterCmvn(out, emb(name))
                assertTrue(cos >= 0.985,
                    "$name: int8-transformer ONNX embedding cosine $cos < 0.985 (functional bar)")
            }
        }
    }

    @Test
    fun full_pipeline_preserves_speaker_invariance() {
        val model = java.io.File(modelPath)
        if (!model.exists()) { println("SKIP: model absent"); return }
        Wav2Vec2Encoder(model.absolutePath).use { enc ->
            val ref = cmvn(enc.encode(float1d("wav/ref_samantha.npy")))
            val cross = cmvn(enc.encode(float1d("wav/crossvoice_daniel.npy")))
            val cost = dtwAlign(ref, cross).normalizedCost
            assertTrue(cost <= 0.18,
                "speaker-invariance cost $cost > 0.18 — int8 broke the touchstone")
        }
    }

    private fun cosAfterCmvn(a: Array<FloatArray>, b: Array<FloatArray>): Double {
        val n = minOf(a.size, b.size)
        val an = cmvn(a.sliceArray(0 until n))
        val bn = cmvn(b.sliceArray(0 until n))
        var dot = 0.0; var na = 0.0; var nb = 0.0
        for (t in 0 until n) for (d in an[t].indices) {
            dot += an[t][d] * bn[t][d]; na += an[t][d] * an[t][d]; nb += bn[t][d] * bn[t][d]
        }
        return dot / (sqrt(na) * sqrt(nb) + 1e-12)
    }
}
