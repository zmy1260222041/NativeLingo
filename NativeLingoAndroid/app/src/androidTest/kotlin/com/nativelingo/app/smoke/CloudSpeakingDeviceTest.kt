package com.nativelingo.app.smoke

import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.nativelingo.app.BuildConfig
import com.nativelingo.app.NativeLingoApp
import com.nativelingo.app.model.AnalyzedSentence
import com.nativelingo.app.model.AnalyzedWord
import com.nativelingo.app.repo.CloudAnalysis
import com.nativelingo.app.repo.CloudClient
import com.nativelingo.app.repo.CloudSpeakingApi
import com.nativelingo.app.repo.WavEncoder
import org.json.JSONObject
import org.junit.Test
import org.junit.runner.RunWith
import kotlinx.coroutines.runBlocking
import kotlin.test.assertEquals
import kotlin.test.assertTrue

private const val TAG_SMOKE = "NLSmoke"

/**
 * End-to-end smoke for the cloud Speaking path (v0.7, Duolingo-style): the
 * server owns transcription, forced alignment, SSL scoring and FR-11 phoneme
 * diagnosis; the client uploads the take (+ the video when the server lacks
 * it) and parses the payload.
 *
 * Same-voice identity (no microphone): the locally-decoded reference segment
 * is uploaded as the learner take, so the DTW of a take against itself must
 * score high — the cloud twin of the pre-migration AnalyzePipelineDeviceTest,
 * and the same trick the studio's "调试:用原声当跟读" uses.
 *
 * v0.7.2: the APK ships with no credential at all — the test registers a
 * throwaway account (random username, so it never collides) and logs in,
 * exactly the app's own flow. Nothing is injected into the test APK.
 *
 * REQUIRES a reachable backend at BuildConfig.SERVER_URL and fails hard when
 * it is unreachable (gate-suite convention — a self-skipping smoke is worse
 * than none). Local development: run the staging backend on the host and
 * rebuild with an override:
 *   cd /tmp/nl-backend-server && .venv/bin/uvicorn backend.main:app --port 8757
 *   ./gradlew :app:assembleDebugAndroidTest \
 *     -PNATIVELINGO_SERVER_URL=http://10.0.2.2:8757
 */
@RunWith(AndroidJUnit4::class)
class CloudSpeakingDeviceTest {

    private val app get() =
        InstrumentationRegistry.getInstrumentation().targetContext.applicationContext as NativeLingoApp
    private val container get() = app.container

    private val api = CloudSpeakingApi(
        CloudClient(tokenProvider = container.tokenStore::loadToken),
    )

    /** Register a throwaway account + log in, once per run (v0.7.2 flow). */
    private fun ensureActivated() {
        if (container.tokenStore.loadToken() != null) return
        val user = "gate_${java.util.UUID.randomUUID().toString().take(8)}"
        val pw = "gatepass${java.util.UUID.randomUUID().toString().take(8)}"
        runBlocking {
            api.registerUser(user, pw)
            val token = api.login(user, pw, container.tokenStore.deviceId())
            container.tokenStore.saveToken(token)
        }
    }

    // ── pure parsing + remapping (no server needed) ──────────────────────────

    @Test
    fun parses_the_analyze_video_payload_including_phoneme_tips() {
        // Wire-shape snapshot of a real /analyze_video response (staging backend).
        // The weak word carries an FR-11 tip; the parse must surface it verbatim.
        val json = JSONObject(
            """
            {
              "overall_score": 74.0, "overall_band": "C", "accuracy": 74.5, "fluency": 73.5,
              "speech_rate_ratio": 0.94,
              "tips": ["Some words need work."],
              "sentences": [
                {
                  "index": 0, "text": "Hello world", "start": 0.12, "end": 2.31,
                  "accuracy": 74.5, "fluency": 73.5,
                  "learner_start": 0.15, "learner_end": 2.40,
                  "words": [
                    {"word": "hello", "start": 0.12, "end": 0.88, "accuracy": 95.0,
                     "status": "good", "tip": "", "learner_start": 0.15, "learner_end": 0.95},
                    {"word": "world", "start": 1.10, "end": 2.31, "accuracy": 54.0,
                     "status": "weak", "tip": "/ɜː/ 读成了 /ɔː/，注意卷舌",
                     "learner_start": 1.20, "learner_end": 2.40}
                  ]
                }
              ]
            }
            """.trimIndent(),
        )
        val a = api.parseAnalysis(json)
        assertEquals(74.0f, a.overallScore)
        assertEquals("C", a.overallBand)
        assertEquals(74.5f, a.accuracy)
        assertEquals(1, a.sentences.size)
        val w = a.sentences[0].words[1]
        assertEquals("world", w.word)
        assertEquals("weak", w.status)
        assertEquals("/ɜː/ 读成了 /ɔː/，注意卷舌", w.tip, "FR-11 phoneme tip must survive the round-trip")
        assertEquals(1.2f, w.learnerStart)
    }

    @Test
    fun remap_shifts_reference_times_but_never_learner_spans() {
        // segStart=10.0 (video timeline), local decode pre-rolls sample-0 to
        // startS=9.5 → shift +0.5. Server times are clip-relative to segStart.
        val a = CloudAnalysis(
            overallScore = 90f, overallBand = "A", accuracy = 90f, fluency = 90f,
            speechRateRatio = 1f, tips = emptyList(),
            sentences = listOf(
                AnalyzedSentence(
                    index = 0, text = "t", start = 1.0f, end = 2.0f,
                    accuracy = 90f, fluency = 90f, learnerStart = 0.5f, learnerEnd = 2.0f,
                    words = listOf(
                        AnalyzedWord(
                            "t", 1.0f, 2.0f, 90f, "good", "",
                            learnerStart = 0.5f, learnerEnd = 2.0f,
                        ),
                    ),
                ),
            ),
        )
        val m = a.remapToLocalReference(segStart = 10.0, refStartS = 9.5)
        val s = m.sentences[0]
        val w = s.words[0]
        assertEquals(1.5f, s.start, "sentence start must shift onto the local decode")
        assertEquals(2.5f, s.end)
        assertEquals(1.5f, w.start)
        assertEquals(2.5f, w.end)
        assertEquals(0.5f, w.learnerStart, "learner spans index the uploaded take — untouched")
        assertEquals(2.0f, w.learnerEnd)
    }

    // ── end-to-end (requires the backend) ────────────────────────────────────

    @Test
    fun ensure_video_and_analyze_same_voice_identity() = runBlocking {
        ensureActivated()
        val video = container.videoRepository.listBundled().first { it.name == "7.1" }

        // The picker grid must be the server's (its indices drive /analyze_video).
        val grid = api.ensureVideo(video.name, container.videoRepository.decodePath(video))
        assertTrue(grid.sentences.isNotEmpty(), "server returned no sentences for 7.1")
        assertTrue(grid.duration > 0.0, "server grid carried no duration")

        // Two short sentences near the start — keeps the upload tiny while still
        // exercising multi-sentence detail projection.
        val startIdx = 0
        val endIdx = minOf(2, grid.sentences.lastIndex)
        val segStart = grid.sentences[startIdx].start.toDouble()
        val segEnd = grid.sentences[endIdx].end.toDouble()

        val ref = container.videoRepository.decodeReferenceSegment(video, segStart, segEnd)
        Log.i(TAG_SMOKE, "decoded 7.1 [%.2f, %.2f]s -> %d samples (startS=%.3f)".format(
            segStart, segEnd, ref.samples.size, ref.startS))

        // Same-voice identity: upload the reference itself as the learner take.
        val cloud = api.analyzeRange(video.name, startIdx, endIdx, WavEncoder.encodePcm16(ref.samples))
        val mapped = cloud.remapToLocalReference(segStart, ref.startS)
        val statuses = mapped.sentences.flatMap { it.words }.groupingBy { it.status }.eachCount()
        Log.i(
            TAG_SMOKE,
            "overall=%.0f acc=%.1f flu=%.1f band=%s sentences=%d words=%s (server %s)".format(
                mapped.overallScore, mapped.accuracy, mapped.fluency, mapped.overallBand,
                mapped.sentences.size, statuses, BuildConfig.SERVER_URL,
            ),
        )

        assertTrue(mapped.sentences.isNotEmpty(), "server returned no sentence detail")
        assertTrue(
            mapped.sentences.any { s -> s.words.any { it.learnerEnd > it.learnerStart } },
            "no word carried a learner replay span — forced alignment failed server-side",
        )
        // Identity: same content, same voice, same audio — the DTW cost is ~0 and
        // the calibrated accuracy lands in the top band (same bar as the old test).
        assertTrue(
            mapped.accuracy >= 75f,
            "same-voice identity accuracy ${mapped.accuracy} should be >= 75 (band good)",
        )
    }
}
