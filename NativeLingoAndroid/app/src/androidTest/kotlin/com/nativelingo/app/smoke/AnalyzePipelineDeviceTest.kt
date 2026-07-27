package com.nativelingo.app.smoke

import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nativelingo.app.NativeLingoApp
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.test.assertTrue

private const val TAG_SMOKE = "NLSmoke"

/**
 * End-to-end smoke for the M1 analyze path that R-12's per-core gate tests do
 * NOT cover: the [com.nativelingo.app.pipeline.AnalyzePipeline] orchestration
 * over a *real* decoded segment of the bundled corpus (MediaCodec decode of
 * `assets/corpus/7.1.mp4` -> encode -> DTW -> score -> detail -> MMS forced-align
 * learner spans -> word_diff), with the new `PauseFeatures` feeding fluency.
 *
 * No microphone: the reference segment is reused as the learner take (same-voice
 * identity). That is the cleanest headless probe — the DTW of a take against
 * itself must score high, and any crash in the wiring (asset-fd decode, the
 * startS-relative sentence projection, the enrichment seam) surfaces here.
 *
 * Models must be present under `filesDir/models` (push_device_models.sh).
 */
@RunWith(AndroidJUnit4::class)
class AnalyzePipelineDeviceTest {

    private val app get() =
        InstrumentationRegistry.getInstrumentation().targetContext.applicationContext as NativeLingoApp
    private val container get() = app.container

    @Test
    fun sameVoice_identity_on_a_real_corpus_segment_scores_high() {
        val video = container.videoRepository.listBundled().first { it.name == "7.1" }
        val sentences = container.videoRepository.loadSentences(video)
        assertTrue(sentences.isNotEmpty(), "bundled 7.1 has no sentences")

        // Two short sentences near the start — keeps the encode fast while still
        // exercising multi-sentence detail projection.
        val startIdx = 0
        val endIdx = minOf(2, sentences.lastIndex)
        val segStart = sentences[startIdx].start.toDouble()
        val segEnd = sentences[endIdx].end.toDouble()
        val selected = sentences.subList(startIdx, endIdx + 1)

        val ref = container.videoRepository.decodeReferenceSegment(video, segStart, segEnd)
        Log.i(TAG_SMOKE, "decoded 7.1 [%.2f, %.2f]s -> %d samples (startS=%.3f)".format(
            segStart, segEnd, ref.samples.size, ref.startS))

        // Same-voice identity: feed the reference back as the learner take.
        val result = container.pipeline.analyzeDetailed(ref, ref.samples.copyOf(), selected)

        val statuses = result.sentences.flatMap { it.words }.groupingBy { it.status }.eachCount()
        Log.i(TAG_SMOKE,
            "overall=%.0f acc=%.1f flu=%.1f band=%s sentences=%d words=%s".format(
                result.overallScore, result.accuracy, result.fluency, result.overallBand,
                result.sentences.size, statuses))

        assertTrue(result.sentences.isNotEmpty(), "pipeline returned no sentence detail")
        assertTrue(result.refSamples.isNotEmpty() && result.learnerSamples.isNotEmpty(),
            "result did not carry replay samples for FR-8")
        // Identity: accuracy must be high. Same content, same voice, same audio —
        // the DTW cost is ~0 and the calibrated accuracy lands in the top band.
        assertTrue(result.accuracy >= 75f,
            "same-voice identity accuracy ${result.accuracy} should be >= 75 (band good)")
    }
}
