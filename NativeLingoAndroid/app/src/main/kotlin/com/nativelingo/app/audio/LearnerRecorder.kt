package com.nativelingo.app.audio

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import java.io.ByteArrayOutputStream
import java.nio.ByteOrder
import kotlin.math.log10
import kotlin.math.sqrt

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
 * by the cloud speaking tests (same-voice identity ≈ 95.0). On the emulator,
 * use the studio's "调试:用原声当跟读" affordance to exercise the results UI
 * without the mic.
 *
 * The caller owns the RECORD_AUDIO runtime permission; [start] assumes it is held.
 *
 * Quiet takes (peak < -12 dBFS) get a linear post-capture boost of up to
 * +12 dB in [stop] — see [normalizeLevel]. Still UNPROCESSED, still no AGC.
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

    /** Stop capture, block until the read loop drains, return samples in [-1, 1],
     *  level-normalised so quiet UNPROCESSED takes still replay audibly. */
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
        val samples = FloatArray(shorts.size) { shorts[it] / 32768.0f }
        return normalizeLevel(samples)
    }

    /**
     * Boost quiet takes to a healthy level with a pure linear gain (up to
     * +12 dB), never clipping. NFR-4④ stays intact — the source is still
     * UNPROCESSED with no AGC/NS colouring; this is a post-capture scale, and
     * every scoring consumer is scale-invariant (R-12 lesson ②: frameDb is
     * relative, stressPos takes positions only, CMVN normalises per dimension;
     * the server also speaker-normalises embeddings), so scores are unchanged
     * while A/B replay and the uploaded WAV both become audible. Takes that
     * are already ≥ -12 dBFS peak pass through untouched (gain = 1).
     */
    private fun normalizeLevel(samples: FloatArray): FloatArray {
        if (samples.isEmpty()) return samples
        var peak = 0f
        var sumSq = 0.0
        for (s in samples) {
            val a = if (s < 0f) -s else s
            if (a > peak) peak = a
            sumSq += s.toDouble() * s
        }
        val gain = when {
            peak <= 0f -> 1f // silence: nothing to boost
            peak < QUIET_PEAK -> minOf(MAX_GAIN, TARGET_PEAK / peak)
            else -> 1f
        }
        Log.i(
            TAG,
            "take peak=%.1f dBFS rms=%.1f dBFS gain=+%.1f dB".format(
                dBfs(peak),
                dBfs(sqrt(sumSq / samples.size.toDouble()).toFloat()),
                20f * log10(gain),
            ),
        )
        if (gain == 1f) return samples
        return FloatArray(samples.size) { samples[it] * gain }
    }

    private fun dBfs(v: Float): Float = if (v <= 0f) -120f else 20f * log10(v)

    companion object {
        const val SAMPLE_RATE = 16_000

        /** Below this peak (-12 dBFS) a take gets boosted. */
        private const val QUIET_PEAK = 0.25f

        /** Cap at +12 dB so a noise floor is not dragged up indefinitely. */
        private const val MAX_GAIN = 4f

        /** Normalise toward 0.85 peak — 1.5 dB headroom below INT16 full scale. */
        private const val TARGET_PEAK = 0.85f

        private const val TAG = "LearnerRecorder"
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
