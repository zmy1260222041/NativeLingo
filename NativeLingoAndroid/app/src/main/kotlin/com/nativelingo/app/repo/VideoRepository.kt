package com.nativelingo.app.repo

import android.content.Context
import com.nativelingo.audio.DecodedAudio
import com.nativelingo.audio.MediaAudioDecoder
import com.nativelingo.scoring.detail.SentenceSpan
import com.nativelingo.scoring.detail.WordSpan
import org.json.JSONObject

/**
 * The corpus: bundled videos (M1) and their pre-computed `.sentences.json`
 * segmentation. The video files themselves ship in `assets/corpus/` (synced from
 * `videos/` at build time — see app/build.gradle.kts), so a fresh install opens
 * with content and zero transcription wait (PRD v0.2 / NFR-3). The bundled path
 * never touches Whisper/VAD — segmentation is read straight from the JSON macOS
 * produced. Imported videos (FR-M2, M2) land here too once `TranscriptionService`
 * writes their `.sentences.json` to filesDir.
 *
 * Sentence/word times in [loadSentences] are **video-relative seconds**, exactly
 * the macOS `videos/<base>.sentences.json` schema. [AnalyzePipeline] converts
 * them to clip-relative against the decoded reference's `startS`.
 */
class VideoRepository(private val appContext: Context) {

    /** A selectable corpus entry. */
    data class CorpusVideo(
        val name: String,          // "7.1" (basename, no extension)
        val assetMp4: String,      // "corpus/7.1.mp4"
        val durationS: Double,
    )

    /** ExoPlayer plays bundled assets via the `asset:///` scheme. */
    fun assetUri(video: CorpusVideo): String = "asset:///${video.assetMp4}"

    /** List the bundled corpus (M1: the synced `videos` mp4s). */
    fun listBundled(): List<CorpusVideo> {
        val names = appContext.assets.list("corpus") ?: emptyArray()
        return names.filter { it.endsWith(".mp4") }.sorted().mapNotNull { file ->
            val base = file.removeSuffix(".mp4")
            val duration = runCatching {
                JSONObject(readAsset("corpus/$base.sentences.json")).optDouble("duration", 0.0)
            }.getOrDefault(0.0)
            CorpusVideo(name = base, assetMp4 = "corpus/$file", durationS = duration)
        }
    }

    /** Load a video's sentence grid (video-relative seconds). Throws if missing. */
    fun loadSentences(video: CorpusVideo): List<SentenceSpan> {
        val json = JSONObject(readAsset("corpus/${video.name}.sentences.json"))
        val arr = json.getJSONArray("sentences")
        val out = ArrayList<SentenceSpan>(arr.length())
        for (i in 0 until arr.length()) {
            val s = arr.getJSONObject(i)
            val words = ArrayList<WordSpan>()
            val warr = s.optJSONArray("words")
            if (warr != null) {
                for (j in 0 until warr.length()) {
                    val w = warr.getJSONObject(j)
                    words.add(WordSpan(w.getString("word"), w.getDouble("start").toFloat(), w.getDouble("end").toFloat()))
                }
            }
            out.add(SentenceSpan(s.getString("text"), s.getDouble("start").toFloat(), s.getDouble("end").toFloat(), words))
        }
        return out
    }

    /**
     * Decode the reference audio for `[segStart, segEnd]` (video-relative) to
     * 16 kHz mono float. Returns [DecodedAudio] whose `startS <= segStart`
     * (MediaCodec pre-roll); [AnalyzePipeline] reconciles sentence times to it.
     * Uses the AssetFileDescriptor overload because a compressed-in-APK asset has
     * no plain filesystem path.
     */
    fun decodeReferenceSegment(video: CorpusVideo, segStart: Double, segEnd: Double): DecodedAudio {
        val afd = appContext.assets.openFd(video.assetMp4)
        return afd.use {
            MediaAudioDecoder.decode(
                it.fileDescriptor, it.startOffset, it.declaredLength,
                startS = segStart, endS = segEnd,
            )
        }
    }

    private fun readAsset(path: String): String =
        appContext.assets.open(path).use { it.readBytes().decodeToString() }
}
