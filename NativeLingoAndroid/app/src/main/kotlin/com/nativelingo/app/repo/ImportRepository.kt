package com.nativelingo.app.repo

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import com.nativelingo.align.ForcedAligner
import com.nativelingo.app.repo.VideoRepository.CorpusVideo
import com.nativelingo.asr.SpeechDetector
import com.nativelingo.asr.WhisperTranscriber
import com.nativelingo.audio.MediaAudioDecoder
import com.nativelingo.scoring.detail.SentenceSpan
import com.nativelingo.scoring.detail.WordSpan
import com.nativelingo.scoring.segment.SentenceSegmenter
import com.nativelingo.scoring.segment.TimedWord
import org.json.JSONObject

/**
 * FR-M2 user-import path: copy a video from a SAF content URI to app-private
 * storage, transcribe it on-device (Whisper base.en + VAD + MMS forced-align),
 * segment into sentences, and cache the result as a `*.sentences.json` in the
 * macOS schema (version 4). A cached video re-appears instantly on next launch.
 *
 * The bundled corpus (PRD v0.2) ships with pre-computed sentences; this is the
 * path for anything the user adds. On-device transcription honours NFR-1
 * (nothing leaves the device — whisper and MMS both run locally).
 */
class ImportRepository(
    private val appContext: Context,
    private val transcriber: WhisperTranscriber,
    private val detector: SpeechDetector,
    private val aligner: ForcedAligner,
) {
    private val dir = java.io.File(appContext.filesDir, "imported").apply { mkdirs() }

    /** Title the UI can show while the copy is in-flight. */
    sealed interface ImportProgress {
        data object Copying : ImportProgress
        data class Decoding(val seconds: Float) : ImportProgress
        data object Transcribing : ImportProgress
        data object Aligning : ImportProgress
        data class Segmenting(val sentences: Int) : ImportProgress
    }

    fun sentencesCache(video: CorpusVideo): java.io.File =
        java.io.File(dir, "${video.name}.sentences.json")

    fun listImported(): List<CorpusVideo> {
        val cacheDir = dir
        return cacheDir.listFiles { f -> reVideo.matches(f.name) }
            ?.sortedBy { it.lastModified() }
            ?.map { f ->
                val base = f.name.removeSuffix(".mp4")
                val dur = runCatching {
                    val json = JSONObject(java.io.File(cacheDir, "$base.sentences.json").readText())
                    json.optDouble("duration", 0.0)
                }.getOrDefault(0.0)
                CorpusVideo(name = base, assetMp4 = null, importPath = f.absolutePath, durationS = dur)
            } ?: emptyList()
    }

    /**
     * Copy a SAF content URI to [destDir] under its display name, then
     * transcribe. Returns the sentences; the `.sentences.json` cache is written
     * in the macOS schema so [VideoRepository.loadSentences] could also read it.
     */
    suspend fun importVideo(
        uri: Uri,
        onProgress: (ImportProgress) -> Unit = {},
    ): Result<List<SentenceSpan>> = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
        runCatching {
            val name = queryDisplayName(uri).removeSuffix(".mp4").replace(Regex("[^a-zA-Z0-9_.-]"), "_")
            val dest = java.io.File(dir, "$name.mp4")
            onProgress(ImportProgress.Copying)
            appContext.contentResolver.openInputStream(uri)?.use { ins ->
                dest.outputStream().use { ins.copyTo(it) }
            } ?: throw IllegalStateException("cannot open URI for read: $uri")
            onProgress(ImportProgress.Decoding(0f))
            val decoded = MediaAudioDecoder.decode(dest.absolutePath)
            val fullWav = decoded.samples
            onProgress(ImportProgress.Transcribing)
            val spans = detector.spans(fullWav)
            onProgress(ImportProgress.Transcribing)
            val transcript = transcriber.transcribe(fullWav, spans)
            val wordList = transcript.text.split(Regex("\\s+")).filter { it.isNotEmpty() }
            if (wordList.isEmpty()) throw IllegalStateException("transcription produced no words")
            onProgress(ImportProgress.Aligning)
            val aligned = aligner.align(wordList, fullWav)
                ?: throw IllegalStateException("forced alignment failed")
            val timedWords = wordList.zip(aligned).mapNotNull { (w, s) ->
                s?.let { TimedWord(w, it.startS.toDouble(), it.endS.toDouble()) }
            }
            onProgress(ImportProgress.Segmenting(timedWords.size))
            val sentences = SentenceSegmenter.mergeIntoSentences(timedWords, subSplit = true)
            onProgress(ImportProgress.Segmenting(sentences.size))

            val json = JSONObject().apply {
                put("version", 4)
                put("video", name)
                put("duration", fullWav.size / 16000.0)
                val sarr = org.json.JSONArray()
                for ((i, s) in sentences.withIndex()) {
                    val sj = org.json.JSONObject().apply {
                        put("index", i)
                        put("start", s.start)
                        put("end", s.end)
                        put("text", s.text)
                        val warr = org.json.JSONArray()
                        for (w in s.words) {
                            warr.put(org.json.JSONObject().apply {
                                put("word", w.word)
                                put("start", w.start)
                                put("end", w.end)
                            })
                        }
                        put("words", warr)
                    }
                    sarr.put(sj)
                }
                put("sentences", sarr)
            }
            java.io.File(dir, "$name.sentences.json").writeText(json.toString(2))
            sentences.map { s ->
                SentenceSpan(s.text, s.start.toFloat(), s.end.toFloat(),
                    s.words.map { WordSpan(it.word, it.start.toFloat(), it.end.toFloat()) })
            }
        }
    }

    private fun queryDisplayName(uri: Uri): String {
        appContext.contentResolver.query(uri, null, null, null, null)?.use { c ->
            val idx = c.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (idx >= 0 && c.moveToFirst()) return c.getString(idx)
        }
        return "imported_${java.lang.System.nanoTime().toString(16)}.mp4"
    }

    companion object {
        private val reVideo = Regex("(?i)\\.(mp4|mov|mkv|m4v|webm)$")
    }
}
