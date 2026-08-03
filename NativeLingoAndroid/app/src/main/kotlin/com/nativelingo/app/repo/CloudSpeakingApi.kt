package com.nativelingo.app.repo

import com.nativelingo.app.model.AnalyzedSentence
import com.nativelingo.app.model.AnalyzedWord
import com.nativelingo.scoring.detail.SentenceSpan
import com.nativelingo.scoring.detail.WordSpan
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File

/**
 * Cloud Speaking API — the Duolingo-style client surface for the self-hosted
 * backend. The server owns reference-clip extraction, transcription, forced
 * alignment, SSL scoring and FR-11 phoneme diagnosis; this class uploads and
 * parses, nothing else. What used to be ImportRepository's local whisper/VAD/MMS
 * work and AnalyzePipeline's in-process scoring are both replaced by these calls.
 *
 * Endpoints (see backend/main.py):
 *  - `POST /videos`        upload a video → sentence grid (v4 schema)
 *  - `POST /analyze_video` upload a learner take → scored payload with per-word
 *                           tips (incl. phoneme substitution, FR-11)
 *  - `GET  /videos`        names available on the server
 *  - `GET  /health`        connectivity/readiness probe
 */
class CloudSpeakingApi(private val client: CloudClient) {

    /**
     * POST /videos — upload a video and get its sentence grid back in one call
     * (the server transcribes + segments immediately, same contract as
     * /videos/{name}/process). [videoName] is the base name (no extension); the
     * local file may be named anything.
     */
    suspend fun uploadVideo(videoPath: String, videoName: String): SentenceGrid =
        withContext(Dispatchers.IO) {
            val json = client.postMultipart(
                "/videos",
                fields = mapOf("name" to "$videoName.mp4"),
                files = listOf("file" to File(videoPath)),
            )
            parseGrid(json)
        }

    /**
     * POST /videos/{name}/process — the sentence grid for a video the server
     * already has (transcription cached on the server).
     */
    suspend fun videoSentences(videoName: String): SentenceGrid =
        withContext(Dispatchers.IO) {
            parseGrid(client.postEmpty("/videos/$videoName.mp4/process"))
        }

    /**
     * Make sure the server can analyze [videoName]: upload [localPath] when it
     * is missing there, otherwise fetch the cached grid. Returns the grid either
     * way — the server is the source of truth for sentence indices, so the
     * picker must show ITS transcription, not the bundled JSON.
     */
    suspend fun ensureVideo(videoName: String, localPath: String): SentenceGrid {
        val onServer = fetchVideoList().any { it == "$videoName.mp4" }
        return if (onServer) videoSentences(videoName) else uploadVideo(localPath, videoName)
    }

    /**
     * POST /analyze_video — score a learner take (16 kHz mono WAV bytes) against
     * a sentence range of a server-side video. Word/sentence `start`/`end` in
     * the result are **clip-relative to the range's segStart on the video
     * timeline**; see [CloudAnalysis.remapToLocalReference] to index a
     * locally-decoded reference (whose sample-0 pre-rolls to an earlier `startS`).
     */
    suspend fun analyzeRange(
        videoName: String,
        startIndex: Int,
        endIndex: Int,
        learnerWav: ByteArray,
    ): CloudAnalysis = withContext(Dispatchers.IO) {
        val json = client.postMultipart(
            "/analyze_video",
            fields = mapOf(
                "video" to "$videoName.mp4",
                "start_index" to startIndex.toString(),
                "end_index" to endIndex.toString(),
            ),
            byteFiles = listOf("learner" to learnerWav),
        )
        parseAnalysis(json)
    }

    /** GET /videos — names available on the server (diagnostics / re-import). */
    suspend fun fetchVideoList(): List<String> = withContext(Dispatchers.IO) {
        val json = client.getJson("/videos")
        val arr = json.optJSONArray("videos") ?: org.json.JSONArray()
        List(arr.length()) { arr.optJSONObject(it).optString("name", "") }
    }

    /**
     * POST /register — device activation (v0.7.1). Exchange a one-time
     * registration code (issued by the operator on the server) for a
     * per-device token. The code is the credential, NOT the APK — the app
     * ships with no key baked in (OWASP Mobile Top 10 M1). The caller stores
     * the token in [TokenStore].
     *
     * Public endpoint by design; [CloudClient] may or may not have a token
     * yet when this is called.
     */
    suspend fun register(deviceId: String, code: String): String =
        withContext(Dispatchers.IO) {
            val json = client.postMultipart(
                "/register",
                fields = mapOf("device_id" to deviceId, "code" to code),
            )
            json.getString("token")
        }

    /** GET /health — connectivity + model readiness probe. */
    suspend fun health(): Boolean = withContext(Dispatchers.IO) {
        runCatching { client.getJson("/health").optString("status") == "ok" }.getOrDefault(false)
    }

    // ── parsing (kept internal so the wire schema lives in one place) ───────

    /** v4 sentence grid: `{version, video, duration, sentences:[…]}`. */
    internal fun parseGrid(json: JSONObject): SentenceGrid {
        val arr = json.optJSONArray("sentences") ?: return SentenceGrid(0.0, emptyList())
        val out = ArrayList<SentenceSpan>(arr.length())
        for (i in 0 until arr.length()) {
            val s = arr.optJSONObject(i) ?: continue
            val words = ArrayList<WordSpan>()
            val warr = s.optJSONArray("words")
            if (warr != null) {
                for (j in 0 until warr.length()) {
                    val w = warr.optJSONObject(j) ?: continue
                    words.add(
                        WordSpan(
                            w.optString("word"),
                            w.optDouble("start", 0.0).toFloat(),
                            w.optDouble("end", 0.0).toFloat(),
                        ),
                    )
                }
            }
            out.add(
                SentenceSpan(
                    s.optString("text"),
                    s.optDouble("start", 0.0).toFloat(),
                    s.optDouble("end", 0.0).toFloat(),
                    words,
                ),
            )
        }
        return SentenceGrid(json.optDouble("duration", 0.0), out)
    }

    /** /analyze_video payload → [CloudAnalysis]. */
    internal fun parseAnalysis(json: JSONObject): CloudAnalysis {
        val tips = ArrayList<String>()
        val tarr = json.optJSONArray("tips")
        if (tarr != null) for (i in 0 until tarr.length()) tips.add(tarr.optString(i))

        val sentences = ArrayList<AnalyzedSentence>()
        val sarr = json.optJSONArray("sentences")
        if (sarr != null) {
            for (i in 0 until sarr.length()) {
                val s = sarr.optJSONObject(i) ?: continue
                val words = ArrayList<AnalyzedWord>()
                val warr = s.optJSONArray("words")
                if (warr != null) {
                    for (j in 0 until warr.length()) {
                        val w = warr.optJSONObject(j) ?: continue
                        words.add(
                            AnalyzedWord(
                                word = w.optString("word"),
                                start = w.optDouble("start", 0.0).toFloat(),
                                end = w.optDouble("end", 0.0).toFloat(),
                                accuracy = w.optDouble("accuracy", 0.0).toFloat(),
                                status = w.optString("status"),
                                tip = w.optString("tip"),
                                learnerStart = w.optDouble("learner_start", 0.0).toFloat(),
                                learnerEnd = w.optDouble("learner_end", 0.0).toFloat(),
                            ),
                        )
                    }
                }
                sentences.add(
                    AnalyzedSentence(
                        index = s.optInt("index", i),
                        text = s.optString("text"),
                        start = s.optDouble("start", 0.0).toFloat(),
                        end = s.optDouble("end", 0.0).toFloat(),
                        accuracy = s.optDouble("accuracy", 0.0).toFloat(),
                        fluency = s.optDouble("fluency", 0.0).toFloat(),
                        learnerStart = s.optDouble("learner_start", 0.0).toFloat(),
                        learnerEnd = s.optDouble("learner_end", 0.0).toFloat(),
                        words = words,
                    ),
                )
            }
        }

        return CloudAnalysis(
            overallScore = json.optDouble("overall_score", 0.0).toFloat(),
            overallBand = json.optString("overall_band"),
            accuracy = json.optDouble("accuracy", 0.0).toFloat(),
            fluency = json.optDouble("fluency", 0.0).toFloat(),
            speechRateRatio = json.optDouble("speech_rate_ratio", 0.0).toFloat(),
            tips = tips,
            sentences = sentences,
        )
    }
}

/**
 * The scored payload from /analyze_video — the cloud twin of
 * [com.nativelingo.app.model.AnalysisResult] minus the audio arrays, which the
 * client fills from its local decode (the video itself stays on-device).
 *
 * Reference-relative times are clip-relative to the requested segStart on the
 * video timeline; learner times index the uploaded take (which IS the client's
 * local recording, so they pass through unchanged).
 */
data class CloudAnalysis(
    val overallScore: Float,
    val overallBand: String,
    val accuracy: Float,
    val fluency: Float,
    val speechRateRatio: Float,
    val tips: List<String>,
    val sentences: List<AnalyzedSentence>,
) {
    /**
     * Map reference times onto a locally-decoded reference clip. The server's
     * times are relative to `segStart` (video timeline); MediaCodec's local
     * decode pre-rolls its sample-0 to `refStartS ≤ segStart`, so
     * `localT = cloudT + (segStart − refStartS)`. Learner spans are already
     * relative to the uploaded take and pass through untouched.
     */
    fun remapToLocalReference(segStart: Double, refStartS: Double): CloudAnalysis {
        val shift = segStart.toFloat() - refStartS.toFloat()
        if (shift == 0f) return this
        val mapped = sentences.map { s ->
            s.copy(
                start = s.start + shift,
                end = s.end + shift,
                words = s.words.map { w -> w.copy(start = w.start + shift, end = w.end + shift) },
            )
        }
        return copy(sentences = mapped)
    }
}

/** v4 sentence grid as returned by the server (sentences + video duration). */
data class SentenceGrid(
    val duration: Double,
    val sentences: List<SentenceSpan>,
)
