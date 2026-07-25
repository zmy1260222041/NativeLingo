package com.nativelingo.align

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import kotlin.math.sqrt

/**
 * The MMS forced-alignment emission model.
 *
 * Runs the HF-re-hosted `MMS_FA` export (`scripts/onnx_export_mms.py`): the
 * torchaudio bundle's own graph could neither be exported cleanly nor quantized
 * (it stayed at 1204MB), so its weights are re-hosted on HF `Wav2Vec2ForCTC`,
 * which quantizes to 338MB — see docs/reviews/2026-07-25-android-gate-b-mms-rehost.md.
 *
 * Three ops that torchaudio's `_Wav2Vec2Model.forward` performs around the
 * network are NOT in the graph, because they are dynamic-shape ops the exporter
 * rejects. They are re-implemented here, and each one is load-bearing:
 *  - [normalizeWaveform] — whole-clip layer_norm. Skipping it does not crash;
 *    it just silently degrades every alignment.
 *  - log_softmax — kept IN the graph (it exports fine).
 *  - the "star" column — MMS_FA appends an all-zero 29th column. Zero in
 *    log-space is log p = 0, i.e. p = 1: a wildcard that can absorb any frame.
 *    We never put star in a target sequence, but the emission width must still
 *    match what the golden was captured with.
 */
class MmsEmitter(modelPath: String) : AutoCloseable {
    private val env: OrtEnvironment = OrtEnvironment.getEnvironment()
    private val session: OrtSession = env.createSession(modelPath, OrtSession.SessionOptions())
    private val inputName: String = session.inputNames.first()
    private val outputName: String = session.outputNames.first()

    /** Raw 16 kHz mono float32 → (T, 29) log-prob emission. */
    fun emission(wav: FloatArray): Array<FloatArray> = runNormalized(normalizeWaveform(wav))

    /** Run on an already-normalized waveform (lets tests isolate the ONNX run). */
    fun runNormalized(normalized: FloatArray): Array<FloatArray> {
        val tensor = OnnxTensor.createTensor(env, arrayOf(normalized)) // (1, N)
        val logits = session.run(mapOf(inputName to tensor)).use { result ->
            @Suppress("UNCHECKED_CAST")
            (result.get(outputName).get().value as Array<Array<FloatArray>>)[0]
        }
        return appendStar(logits)
    }

    override fun close() = session.close()
}

/** MMS_FA's star column: V 28 → 29, all zeros. */
fun appendStar(emission: Array<FloatArray>): Array<FloatArray> =
    Array(emission.size) { t ->
        val row = emission[t]
        FloatArray(row.size + 1) { if (it < row.size) row[it] else 0f }
    }

/**
 * torchaudio's `F.layer_norm(waveforms, waveforms.shape)` — zero-mean,
 * unit-variance over the WHOLE clip with no affine transform.
 *
 * Note the eps differs from the SSL encoder's: layer_norm's default is 1e-5,
 * while `Wav2Vec2FeatureExtractor` (:core-embed) uses 1e-7. They look
 * interchangeable and are not; each matches its own upstream.
 */
private const val LAYER_NORM_EPS = 1e-5

fun normalizeWaveform(wav: FloatArray): FloatArray {
    if (wav.isEmpty()) return wav
    var mean = 0.0
    for (v in wav) mean += v.toDouble()
    mean /= wav.size
    var varSum = 0.0
    for (v in wav) { val d = v.toDouble() - mean; varSum += d * d }
    val denom = sqrt(varSum / wav.size + LAYER_NORM_EPS)
    return FloatArray(wav.size) { ((wav[it].toDouble() - mean) / denom).toFloat() }
}
