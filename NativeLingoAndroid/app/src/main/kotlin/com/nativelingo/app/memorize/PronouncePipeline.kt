package com.nativelingo.app.memorize

import com.nativelingo.embed.Wav2Vec2Encoder
import com.nativelingo.scoring.align.dtwAlign
import com.nativelingo.scoring.audio.AudioPreproc
import com.nativelingo.scoring.audio.PauseFeatures
import com.nativelingo.scoring.norm.normalizePair
import com.nativelingo.scoring.resample.PolyphaseResampler
import com.nativelingo.scoring.score.Calibration
import com.nativelingo.scoring.score.scoreTrackB
import kotlin.math.roundToLong

/**
 * Word/phrase pronunciation scoring for the Memorizing module (FR-17) — the
 * slice of the desktop pipeline's `analyze_detailed` that is independent of the
 * video sentence grid: embed → CMVN pair → DTW → Track B score. It stayed
 * on-device when the Speaking track moved to the cloud (v0.7) — 识物 never
 * uploads.
 *
 * The reference is the Piper-synthesized audio of the target word/phrase (what
 * the user just heard via `/memorize/tts`), and the learner is their recording.
 * No forced alignment, no sentence detail, no word-diff — those belong to the
 * video shadowing track, which has a transcript grid to project onto. Here the
 * unit is one word or short phrase, scored as a whole.
 *
 * This mirrors desktop `backend/core/pipeline.py:analyze_arrays` (the path
 * `/memorize/pronounce` uses), returning the same three numbers: accuracy,
 * fluency, speech_rate_ratio.
 *
 * @param targetSampleRate the rate the SSL encoder expects (16000). Piper's
 *   native output (22050) is resampled to this before scoring.
 */
class PronouncePipeline(
    private val encoder: Wav2Vec2Encoder,
    private val calibration: Calibration,
    private val targetSampleRate: Int = 16_000,
) {

    /** The scored result — the shape of desktop `/memorize/pronounce`. */
    data class Score(
        val accuracy: Float,         // 0-100, rounded 1 dp
        val fluency: Float,          // 0-100, rounded 1 dp
        val speechRateRatio: Float,  // learner_dur / ref_dur, rounded 3 dp
    )

    /**
     * Score [learnerSamples] (at [targetSampleRate]) against [refSamples] (at
     * [refSampleRate], resampled if needed). Both are mono float32.
     *
     * The learner audio is silence-trimmed first (matching the desktop
     * `analyze_arrays` path); the reference is used as-is (Piper output has no
     * leading silence to trim).
     */
    fun score(
        refSamples: FloatArray,
        refSampleRate: Int,
        learnerSamples: FloatArray,
    ): Score {
        val ref = if (refSampleRate == targetSampleRate) refSamples
            else PolyphaseResampler.resample(refSamples, refSampleRate, targetSampleRate)

        val learnerTrim = AudioPreproc.trimSilenceWithOffset(learnerSamples).wav

        val refEmb = encoder.encode(ref)
        val learnerEmb = encoder.encode(learnerTrim)
        val (refN, learnerN) = normalizePair(refEmb, learnerEmb)
        val dtw = dtwAlign(refN, learnerN)

        val (pausePerS, pauseRatio) = PauseFeatures.fluencyInputs(learnerTrim)
        val trackB = scoreTrackB(
            dtw.path, dtw.pathCosts, dtw.normalizedCost,
            refLen = refEmb.size, learnerLen = learnerEmb.size,
            pausePerS = pausePerS.toFloat(), pauseRatio = pauseRatio.toFloat(),
            calibration = calibration,
        )
        val refDurSec = ref.size.toDouble() / targetSampleRate
        val learnerDurSec = learnerTrim.size.toDouble() / targetSampleRate
        val rateRatio = (learnerDurSec / refDurSec.coerceAtLeast(1e-6)).toFloat()
        return Score(
            accuracy = round1(trackB.accuracy),
            fluency = round1(trackB.fluency),
            speechRateRatio = round3(rateRatio),
        )
    }

    private fun round1(v: Float): Float = (v * 10f).roundToLong() / 10f
    private fun round3(v: Float): Float = (v * 1000f).roundToLong() / 1000f
}
