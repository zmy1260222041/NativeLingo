package com.nativelingo.asr

import com.k2fsa.sherpa.onnx.FeatureConfig
import com.k2fsa.sherpa.onnx.OfflineModelConfig
import com.k2fsa.sherpa.onnx.OfflineRecognizer
import com.k2fsa.sherpa.onnx.OfflineRecognizerConfig
import com.k2fsa.sherpa.onnx.OfflineWhisperModelConfig
import com.nativelingo.scoring.segment.AsrWindowPlanner

/** One recognizer call: the text of `[startSample, endSample)`. */
data class TranscribedWindow(val startSample: Int, val endSample: Int, val text: String)

/**
 * The transcript of a clip. [text] is what FR-2 consumes; [windows] is kept for
 * diagnostics (Layer-3 sidecar) because which window a sentence came from is the
 * first thing to look at when a practice unit boundary looks wrong.
 */
data class Transcript(val text: String, val windows: List<TranscribedWindow>)

/**
 * Whisper `base.en` via sherpa-onnx (FR-2).
 *
 * **Text only.** Word boundaries come from MMS forced alignment in `:core-align`
 * — Whisper's own word timestamps clip the ends of short words (see
 * `forced_align.py`, migration §4 discovery ⑤). On Android the point is moot
 * anyway: the v1.13.4 AAR returns empty `timestamps` for the stock models and
 * exposes no segment timestamps at all, so `text` is genuinely all there is.
 *
 * The model files are the ones R-10 measured — `base.en-{encoder,decoder}.int8.onnx`.
 * int8 is confirmed, not provisional: fp32 buys 0.11pp WER for 132MB and is not
 * even faster (the decoder is memory-bound on an fp32 token-embedding table), so
 * unlike :core-embed there is no fp32 fallback path to keep alive here.
 */
class WhisperTranscriber(
    encoderPath: String,
    decoderPath: String,
    tokensPath: String,
    numThreads: Int = 4,
) : AutoCloseable {

    private val recognizer = OfflineRecognizer(
        assetManager = null,
        config = OfflineRecognizerConfig(
            featConfig = FeatureConfig(sampleRate = SAMPLE_RATE, featureDim = 80),
            modelConfig = OfflineModelConfig(
                whisper = OfflineWhisperModelConfig(
                    encoder = encoderPath,
                    decoder = decoderPath,
                    language = "en",
                    task = "transcribe",
                ),
                tokens = tokensPath,
                numThreads = numThreads,
                modelType = "whisper",
            ),
        ),
    )

    /**
     * Transcribe a whole clip, cutting it where [spans] allow.
     *
     * The recognizer takes 30 s at most, so long audio has to be cut, and R-10
     * measured that *how* it is cut moves WER by 2.4pp and the practice-unit
     * count by 14 — Whisper punctuates the end of whatever it is handed, so a
     * cut mid-sentence invents a sentence end. Hence: merge VAD spans into ≤29 s
     * windows ([AsrWindowPlanner]) and decode each window's *contiguous* audio,
     * internal silences included. Never splice speech regions together — that
     * butts phrases against each other that never met, and Whisper punctuates
     * the seam.
     */
    fun transcribe(
        samples: FloatArray,
        spans: List<AsrWindowPlanner.Span>,
        onOverlongWindow: (AsrWindowPlanner.Window) -> Unit = {},
    ): Transcript {
        val windows = AsrWindowPlanner.plan(spans)
        AsrWindowPlanner.overlong(windows, SAMPLE_RATE).forEach(onOverlongWindow)
        val out = windows.map { w ->
            val end = minOf(w.end, samples.size)
            TranscribedWindow(w.start, end, decode(samples.copyOfRange(w.start, end)))
        }
        return Transcript(
            text = out.joinToString(" ") { it.text.trim() }.trim(),
            windows = out,
        )
    }

    /**
     * One recognizer call over the given samples.
     *
     * Public because the learner path uses it directly: a shadowing recording is
     * one sentence of a few seconds, so there is nothing to window, and running
     * VAD over it would only risk trimming the learner's own hesitant onset.
     * Audio beyond 30 s is truncated by the recognizer with only a native-log
     * warning — the caller is responsible for not getting there.
     */
    fun decode(samples: FloatArray): String {
        val stream = recognizer.createStream()
        return try {
            stream.acceptWaveform(samples, SAMPLE_RATE)
            recognizer.decode(stream)
            recognizer.getResult(stream).text
        } finally {
            stream.release()
        }
    }

    override fun close() = recognizer.release()

    companion object {
        const val SAMPLE_RATE = 16_000
    }
}
