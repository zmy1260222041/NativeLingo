package com.nativelingo.app.audio

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import java.io.ByteArrayOutputStream
import java.nio.ByteOrder

/**
 * FR-3 capture: 16 kHz mono PCM via [AudioRecord] with [MediaRecorder.AudioSource.UNPROCESSED]
 * (NFR-4④ — no AGC/NS colouring, so the take scores against the reference
 * faithfully). R-9 settled that the learner path never produces encoded audio:
 * AudioRecord yields PCM directly, so there is no codec round-trip to account for.
 *
 * **Emulator caveat:** the Android emulator's microphone is unusable for scoring
 * — a capture probe (`CaptureProbeDeviceTest`) shows it delivers either
 * full-scale-clipped garbage (a square wave → the "电流音" buzz) or near-silence,
 * never clean speech. That is the emulator's audio backend, not this code, and
 * not fixable from the app (AudioRecord can't trim the emulator's preamp gain).
 * Real devices capture cleanly; the analyze path itself is verified end-to-end
 * by `AnalyzePipelineDeviceTest` (95.0, same-voice identity). On the emulator,
 * use the studio's "调试:用原声当跟读" affordance to exercise the results UI
 * without the mic.
 *
 * The caller owns the RECORD_AUDIO runtime permission; [start] assumes it is held.
 */
class LearnerRecorder {

    @Volatile private var recording = false
    private var record: AudioRecord? = null
    private var thread: Thread? = null

    val isRecording: Boolean get() = recording

    /**
     * Begin capture. Returns immediately; recording runs on a background thread.
     * [stop] joins and returns the captured samples in [-1, 1].
     */
    fun start() {
        check(!recording) { "already recording" }
        val minBuf = AudioRecord.getMinBufferSize(SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val ar = AudioRecord(
            MediaRecorder.AudioSource.UNPROCESSED,
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            maxOf(minBuf * 2, SAMPLE_RATE * 2), // frames * 2 bytes (mono 16-bit)
        )
        check(ar.state == AudioRecord.STATE_INITIALIZED) { "AudioRecord not initialised (permission? busy?)" }
        record = ar
        recording = true
        ar.startRecording()
        val sink = ByteArrayOutputStream()
        thread = Thread({
            val chunk = ShortArray(1024)
            while (recording) {
                val n = ar.read(chunk, 0, chunk.size)
                if (n > 0) {
                    // Little-endian PCM_16 bytes — AudioRecord's native byte order on Android.
                    for (i in 0 until n) {
                        sink.write(chunk[i].toInt() and 0xFF)
                        sink.write(chunk[i].toInt() shr 8 and 0xFF)
                    }
                }
            }
            pending = sink.toByteArray()
        }, "nlg-audio-capture").apply { start() }
    }

    private var pending: ByteArray = ByteArray(0)

    /** Stop capture, block until the read loop drains, return samples in [-1, 1]. */
    fun stop(): FloatArray {
        recording = false
        thread?.join(2000)
        record?.stop()
        record?.release()
        record = null
        thread = null
        val bytes = pending
        pending = ByteArray(0)
        val shorts = ByteBufferCompat.toShortArray(bytes)
        return FloatArray(shorts.size) { shorts[it] / 32768.0f }
    }

    companion object {
        const val SAMPLE_RATE = 16_000
    }
}

/** Read a little-endian byte stream into shorts without pulling in java.nio boilerplate at call sites. */
private object ByteBufferCompat {
    fun toShortArray(bytes: ByteArray): ShortArray {
        val out = ShortArray(bytes.size / 2)
        val bb = java.nio.ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        bb.asShortBuffer().get(out)
        return out
    }
}
