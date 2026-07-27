package com.nativelingo.app.repo

import android.content.Context
import com.nativelingo.scoring.io.WavIo
import java.io.File

/**
 * Persists learner takes as 16 kHz mono PCM WAV in app-private storage. FR-8
 * replay slices these (or the in-memory [com.nativelingo.app.model.AnalysisResult.learnerSamples])
 * sample-accurately — macOS does the same server-side via `/recordings/{rid}/clip`;
 * here it is a local file cut. M1 mostly replays from the in-memory result held by
 * the results ViewModel; this store keeps the take across process death and is
 * the seam FR-12 history will read from later.
 */
class RecordingsRepository(context: Context) {
    private val dir = File(context.filesDir, "recordings").apply { mkdirs() }

    fun store(samples: FloatArray, sampleRate: Int = 16000): File {
        val id = System.nanoTime().toString(16)
        val file = File(dir, "$id.wav")
        file.outputStream().use { it.write(WavIo.writePcm16(samples, sampleRate)) }
        return file
    }
}
