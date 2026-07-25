package com.nativelingo.asr

import com.k2fsa.sherpa.onnx.SileroVadModelConfig
import com.k2fsa.sherpa.onnx.Vad
import com.k2fsa.sherpa.onnx.VadModelConfig
import com.nativelingo.scoring.segment.AsrWindowPlanner

/**
 * Silero VAD — where the speech is.
 *
 * Two callers, two very different jobs:
 *  - the reference path uses [spans] to decide where transcription may cut
 *    (`AsrWindowPlanner`), which is the decision R-10 found dominates transcript
 *    quality;
 *  - the recording path (FR-3) uses it to answer "is anyone talking", where the
 *    spans are one short utterance and no windowing is involved.
 *
 * The knobs mirror `scripts/asr_text_parity.py`, which is what the Gate F
 * numbers were measured with — changing one here invalidates that measurement.
 */
class SpeechDetector(
    modelPath: String,
    sampleRate: Int = 16_000,
    numThreads: Int = 1,
) : AutoCloseable {

    private val config = VadModelConfig(
        sileroVadModelConfig = SileroVadModelConfig(
            model = modelPath,
            threshold = 0.5f,
            minSilenceDuration = 0.25f,
            minSpeechDuration = 0.25f,
            // Asked for, not honoured: R-10 measured spans of 29.9 s and 30.2 s
            // out of a 25 s cap. sherpa-onnx treats it as a hint, so callers
            // must still handle over-length spans — see AsrWindowPlanner.
            maxSpeechDuration = 25.0f,
        ),
        sampleRate = sampleRate,
        numThreads = numThreads,
    )

    private val vad = Vad(assetManager = null, config = config)

    /**
     * Speech spans over the whole waveform, in samples.
     *
     * Feeding is chunked at the model's own window size because that is the unit
     * Silero scores; sherpa buffers internally and emits segments as they close,
     * hence the drain-after-each-push shape and the [Vad.flush] at the end (the
     * last segment never closes on its own — a missing flush silently drops the
     * final utterance, which is the tail of every clip).
     */
    fun spans(samples: FloatArray): List<AsrWindowPlanner.Span> {
        vad.reset()
        val out = ArrayList<AsrWindowPlanner.Span>()
        val window = config.sileroVadModelConfig.windowSize
        var i = 0
        while (i < samples.size) {
            vad.acceptWaveform(samples.copyOfRange(i, minOf(i + window, samples.size)))
            drain(out)
            i += window
        }
        vad.flush()
        drain(out)
        return out
    }

    private fun drain(out: MutableList<AsrWindowPlanner.Span>) {
        while (!vad.empty()) {
            val seg = vad.front()
            out.add(AsrWindowPlanner.Span(seg.start, seg.samples.size))
            vad.pop()
        }
    }

    override fun close() = vad.release()
}
