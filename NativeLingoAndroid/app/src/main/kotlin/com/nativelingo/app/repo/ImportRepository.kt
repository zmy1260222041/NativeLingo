package com.nativelingo.app.repo

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import com.nativelingo.app.repo.VideoRepository.CorpusVideo
import com.nativelingo.scoring.detail.SentenceSpan
import org.json.JSONObject

/**
 * FR-M2 user-import path, cloud architecture: copy a video from a SAF content
 * URI to app-private storage, upload it to the NativeLingo server, and let the
 * server transcribe + sentence-segment it (whisper + VAD + MMS all live
 * server-side now — Duolingo-style). The server's grid is cached as a
 * `*.sentences.json` in the macOS v4 schema so the imported video re-appears
 * instantly on next launch, and the local copy stays for muted playback and
 * A/B reference decode.
 *
 * On-device transcription is gone: the import is only as fast as the upload.
 */
class ImportRepository(
    private val appContext: Context,
    private val cloud: CloudSpeakingApi,
) {
    private val dir = java.io.File(appContext.filesDir, "imported").apply { mkdirs() }

    /** Title the UI can show while the copy is in-flight. */
    sealed interface ImportProgress {
        data object Copying : ImportProgress
        data object Uploading : ImportProgress
        data object Transcribing : ImportProgress  // server-side (whisper + VAD + MMS)
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
     * Copy a SAF content URI to [destDir] under its display name, then upload to
     * the server for transcription. Returns the server's sentences; the
     * `.sentences.json` cache is written in the macOS v4 schema so
     * [VideoRepository.loadSentences] could also read it.
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
            onProgress(ImportProgress.Uploading)
            val grid = cloud.uploadVideo(dest.absolutePath, name)
            onProgress(ImportProgress.Transcribing)
            if (grid.sentences.isEmpty()) throw IllegalStateException("服务器转写未产生句子")
            onProgress(ImportProgress.Segmenting(grid.sentences.size))

            writeCache(name, grid)
            grid.sentences
        }
    }

    /** Cache the server grid in the macOS v4 schema (same shape the bundled
     * corpus ships with, so any consumer that reads one reads the other). */
    private fun writeCache(name: String, grid: SentenceGrid) {
        val json = JSONObject().apply {
            put("version", 4)
            put("video", name)
            put("duration", grid.duration)
            val sarr = org.json.JSONArray()
            for ((i, s) in grid.sentences.withIndex()) {
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
