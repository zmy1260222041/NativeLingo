package com.nativelingo.audio

import android.media.MediaCodec
import android.media.MediaCodecList
import android.media.MediaExtractor
import android.media.MediaFormat
import com.nativelingo.scoring.resample.PolyphaseResampler
import java.io.FileDescriptor
import java.nio.ByteOrder

/** Decoded audio plus where it actually starts, in the source's timeline. */
data class DecodedAudio(
    /** 16 kHz (or [sampleRate]) mono float32, in [-1, 1]. */
    val samples: FloatArray,
    val sampleRate: Int,
    /**
     * Timestamp of `samples[0]` in the source. Seeking lands on the sync sample
     * at or before the requested start, and those pre-start samples are kept
     * (macOS does the same — `video.py:extract_audio`'s "any pre-start samples
     * decoded are kept"), so this is ≤ the requested start and the caller needs
     * it to place FR-8 replay spans.
     */
    val startS: Double,
) {
    override fun equals(other: Any?): Boolean =
        this === other || (other is DecodedAudio &&
            samples.contentEquals(other.samples) &&
            sampleRate == other.sampleRate && startS == other.startS)

    override fun hashCode(): Int =
        (samples.contentHashCode() * 31 + sampleRate) * 31 + startS.hashCode()
}

/** No decoder on this device for the track's codec, or no audio track at all. */
class UnsupportedAudioException(message: String) : RuntimeException(message)

/**
 * Decodes a media file's first audio track to 16 kHz mono float32 — the Android
 * counterpart of `backend/core/video.py:extract_audio`.
 *
 * ### Why the platform decoder and not FFmpeg
 *
 * The original plan built FFmpeg from source with the NDK, on the premise that
 * "MediaCodec's WebM/Opus coverage is incomplete". R-9 found that premise void:
 * the learner path never produces encoded audio at all on Android (AudioRecord
 * captures 16 kHz PCM directly — webm/opus was a WebView `MediaRecorder`
 * artifact), and Opus decoding has been a *mandatory* platform feature since
 * API 21, far below our minSdk 28. Only `.avi` is outside the platform's
 * guarantees, and that is an import-support gap, not a correctness one.
 *
 * The cost of this choice, stated plainly: FFmpeg is the same bytes on every
 * device, whereas system decoders are per-OEM implementations. R-9 measured
 * that a *much* larger perturbation — swapping the resampling kernel entirely,
 * ~40 dB SNR — moves the DTW cost by ≤0.0011 against a ±0.02 tolerance, so
 * decoder-to-decoder variation is very likely irrelevant. "Very likely" is an
 * inference, not a measurement; multi-device decode consistency is on the
 * device checklist. See `docs/reviews/2026-07-26-android-gate-e-audio-decode.md`.
 */
object MediaAudioDecoder {

    const val TARGET_SR = 16_000

    private const val TIMEOUT_US = 10_000L

    /** Decode `[startS, endS]` (whole track when both are null) from a path. */
    fun decode(
        path: String,
        startS: Double? = null,
        endS: Double? = null,
        targetSr: Int = TARGET_SR,
    ): DecodedAudio = MediaExtractor().use { it.setDataSource(path); decode(it, startS, endS, targetSr) }

    /** Same, for a content URI opened by the caller (FR-M2 SAF import). */
    fun decode(
        fd: FileDescriptor,
        offset: Long,
        length: Long,
        startS: Double? = null,
        endS: Double? = null,
        targetSr: Int = TARGET_SR,
    ): DecodedAudio =
        MediaExtractor().use { it.setDataSource(fd, offset, length); decode(it, startS, endS, targetSr) }

    private inline fun <R> MediaExtractor.use(block: (MediaExtractor) -> R): R =
        try { block(this) } finally { release() }

    private fun decode(
        extractor: MediaExtractor,
        startS: Double?,
        endS: Double?,
        targetSr: Int,
    ): DecodedAudio {
        val track = (0 until extractor.trackCount).firstOrNull { i ->
            extractor.getTrackFormat(i).getString(MediaFormat.KEY_MIME)?.startsWith("audio/") == true
        } ?: throw UnsupportedAudioException("no audio track in container")

        val format = extractor.getTrackFormat(track)
        val mime = format.getString(MediaFormat.KEY_MIME)!!
        // Probe before configuring: `createDecoderByType` throws a bare
        // IOException, which reads as "the file is broken" rather than "this
        // device has no decoder for it". FR-M2 needs to tell those apart.
        MediaCodecList(MediaCodecList.REGULAR_CODECS).findDecoderForFormat(format)
            ?: throw UnsupportedAudioException("no decoder on this device for $mime")

        extractor.selectTrack(track)
        if (startS != null && startS > 0.0) {
            // SEEK_TO_PREVIOUS_SYNC, and we keep what it gives us — see
            // DecodedAudio.startS.
            extractor.seekTo((startS * 1_000_000).toLong(), MediaExtractor.SEEK_TO_PREVIOUS_SYNC)
        }
        val endUs = endS?.let { (it * 1_000_000).toLong() }

        val codec = MediaCodec.createDecoderByType(mime)
        val pcm = ArrayList<FloatArray>()
        var total = 0
        var srcRate = format.getInteger(MediaFormat.KEY_SAMPLE_RATE)
        var firstPtsUs = -1L
        try {
            codec.configure(format, null, null, 0)
            codec.start()

            var inputDone = false
            var outputDone = false
            var channels = format.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
            var floatPcm = false

            while (!outputDone) {
                if (!inputDone) {
                    val inIdx = codec.dequeueInputBuffer(TIMEOUT_US)
                    if (inIdx >= 0) {
                        val buf = codec.getInputBuffer(inIdx)!!
                        val size = extractor.readSampleData(buf, 0)
                        val pts = extractor.sampleTime
                        if (size < 0 || (endUs != null && pts > endUs)) {
                            codec.queueInputBuffer(
                                inIdx, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM,
                            )
                            inputDone = true
                        } else {
                            codec.queueInputBuffer(inIdx, 0, size, pts, 0)
                            extractor.advance()
                        }
                    }
                }

                val info = MediaCodec.BufferInfo()
                when (val outIdx = codec.dequeueOutputBuffer(info, TIMEOUT_US)) {
                    MediaCodec.INFO_OUTPUT_FORMAT_CHANGED -> {
                        // Authoritative rate/layout: the *output* format, not the
                        // track's. A decoder is free to hand back something else.
                        val out = codec.outputFormat
                        srcRate = out.getInteger(MediaFormat.KEY_SAMPLE_RATE)
                        channels = out.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
                        floatPcm = out.containsKey(MediaFormat.KEY_PCM_ENCODING) &&
                            out.getInteger(MediaFormat.KEY_PCM_ENCODING) == 4 // ENCODING_PCM_FLOAT
                    }
                    MediaCodec.INFO_TRY_AGAIN_LATER -> Unit
                    else -> if (outIdx >= 0) {
                        if (info.size > 0) {
                            if (firstPtsUs < 0) firstPtsUs = info.presentationTimeUs
                            val buf = codec.getOutputBuffer(outIdx)!!
                            buf.position(info.offset)
                            buf.limit(info.offset + info.size)
                            val mono = toMono(buf, channels, floatPcm)
                            pcm.add(mono)
                            total += mono.size
                        }
                        codec.releaseOutputBuffer(outIdx, false)
                        if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) outputDone = true
                    }
                }
            }
        } finally {
            runCatching { codec.stop() }
            codec.release()
        }

        val joined = FloatArray(total)
        var at = 0
        for (chunk in pcm) { chunk.copyInto(joined, at); at += chunk.size }

        val resampled = PolyphaseResampler.resample(joined, srcRate, targetSr)
        return DecodedAudio(
            samples = resampled,
            sampleRate = targetSr,
            startS = if (firstPtsUs < 0) 0.0 else firstPtsUs / 1_000_000.0,
        )
    }

    /**
     * Interleaved PCM → mono float32 in [-1, 1], averaging channels.
     *
     * Averaging is what libswresample's `layout="mono"` downmix does for plain
     * stereo, which is the case that occurs here; it is not a general
     * multichannel downmix (no centre/LFE weighting) and does not need to be —
     * `videos/` material is stereo or mono.
     */
    private fun toMono(buf: java.nio.ByteBuffer, channels: Int, floatPcm: Boolean): FloatArray {
        buf.order(ByteOrder.nativeOrder())
        val ch = if (channels < 1) 1 else channels
        return if (floatPcm) {
            val f = buf.asFloatBuffer()
            val n = f.remaining() / ch
            FloatArray(n) { i ->
                var acc = 0.0f
                for (c in 0 until ch) acc += f.get(i * ch + c)
                acc / ch
            }
        } else {
            val s = buf.asShortBuffer()
            val n = s.remaining() / ch
            FloatArray(n) { i ->
                var acc = 0.0f
                for (c in 0 until ch) acc += s.get(i * ch + c) / 32768.0f
                acc / ch
            }
        }
    }
}
