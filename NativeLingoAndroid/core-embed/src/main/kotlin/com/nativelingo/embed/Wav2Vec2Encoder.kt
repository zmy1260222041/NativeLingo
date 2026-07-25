package com.nativelingo.embed

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import kotlin.math.sqrt

/**
 * The Android SSL encoder — runs the int8-transformer ONNX export of
 * facebook/wav2vec2-base-960h (transformer layers 6-9 mean, CNN feature
 * extractor in fp32; see docs/reviews/2026-07-25-android-gate-a-onnx-int8.md)
 * via onnxruntime. Returns (T, 768) frame embeddings — the input to the
 * :core-scoring DTW.
 */
class Wav2Vec2Encoder(modelPath: String) : AutoCloseable {
    private val env: OrtEnvironment = OrtEnvironment.getEnvironment()
    private val session: OrtSession = env.createSession(modelPath, OrtSession.SessionOptions())
    private val inputName: String = session.inputNames.first()
    private val outputName: String = session.outputNames.first()

    /** Normalize + run. ``wav`` is raw 16 kHz mono float32. */
    fun encode(wav: FloatArray): Array<FloatArray> = runNormalized(normalizeWav2Vec2(wav))

    /** Run on a pre-normalized input (the feature-extractor output). */
    fun runNormalized(normalized: FloatArray): Array<FloatArray> {
        val tensor = OnnxTensor.createTensor(env, arrayOf(normalized)) // (1, N)
        return session.run(mapOf(inputName to tensor)).use { result ->
            // output shape (1, T, 768) → batch 0 → (T, 768)
            @Suppress("UNCHECKED_CAST")
            (result.get(outputName).get().value as Array<Array<FloatArray>>)[0]
        }
    }

    override fun close() = session.close()
}

/**
 * Wav2Vec2FeatureExtractor normalization (do_normalize=true): zero-mean,
 * unit-variance (population), eps 1e-7 — applied to the raw waveform before the
 * ONNX model. Top-level so it's testable without a session.
 */
private const val VAR_EPS = 1e-7

fun normalizeWav2Vec2(wav: FloatArray): FloatArray {
    if (wav.isEmpty()) return wav
    var mean = 0.0
    for (v in wav) mean += v.toDouble()
    mean /= wav.size
    var varSum = 0.0
    for (v in wav) { val d = v.toDouble() - mean; varSum += d * d }
    val denom = sqrt(varSum / wav.size + VAR_EPS)
    return FloatArray(wav.size) { ((wav[it].toDouble() - mean) / denom).toFloat() }
}
