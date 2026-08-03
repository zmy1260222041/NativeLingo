package com.nativelingo.app.smoke

import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nativelingo.app.gates.DeviceFixtures
import com.nativelingo.app.memorize.PronouncePipeline
import com.nativelingo.app.repo.ReferenceClipSource
import com.nativelingo.models.ModelId
import com.nativelingo.embed.Wav2Vec2Encoder
import com.nativelingo.scoring.score.CalibrationLoader
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.test.assertTrue

/**
 * End-to-end gate for the Memorizing pronunciation score (FR-17, Option D).
 *
 * Loads the pre-rendered "cat" reference clip, uses it as BOTH the reference and
 * the learner audio (a self-match), and asserts the Track B pipeline returns a
 * high accuracy score. A self-match is the cleanest correctness signal: the
 * wav2vec2 embeddings, CMVN pair, DTW and calibration are all exercised on real
 * arm64 inference, and the only thing that can make the score low is a bug in
 * the port — not pronunciation quality.
 *
 * This is the gate that proves the whole Option-D chain hangs together:
 * reference clip → ReferenceClipSource → PronouncePipeline → SSL encoder →
 * DTW → calibrated score, all on-device, offline.
 */
@RunWith(AndroidJUnit4::class)
class MemorizePronounceDeviceTest {

    @Test
    fun self_match_scores_high() {
        val modelFile = DeviceFixtures.requireModel(ModelId.SSL_ENCODER)
        val clips = ReferenceClipSource(DeviceFixtures.appContext)

        val reference = clips.synthesize("cat")
        assertTrue(reference != null && reference.isNotEmpty(), "'cat' reference clip missing")

        val encoder = Wav2Vec2Encoder(modelFile.absolutePath)
        val calibration = CalibrationLoader.loadDefault()
        val pipeline = PronouncePipeline(encoder, calibration)

        // Self-match: learner == reference. Accuracy should be near-perfect.
        val score = pipeline.score(reference, 16_000, reference)
        assertTrue(score.accuracy >= 85f,
            "self-match accuracy ${score.accuracy} < 85 — pipeline port is broken (expected near-100)")
        assertTrue(score.fluency >= 80f,
            "self-match fluency ${score.fluency} < 80 — fluency features miscomputed")
        // Rate ratio of a self-match is ~1.0 (same audio, same length).
        assertTrue(score.speechRateRatio in 0.95f..1.05f,
            "self-match rate ratio ${score.speechRateRatio} should be ~1.0")

        encoder.close()
    }
}
