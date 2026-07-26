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
     * Timestamp of `samples[0]` in the source, which is at or before the
     * requested start — the caller needs it to place FR-8 replay spans, and
     * pre-start samples are kept rather than trimmed (macOS does the same, see
     * `video.py:extract_audio`'s "any pre-start samples decoded are kept").
     *
     * Being ≤ the request is not free, and not what a plain seek gives you.
     * Measured on device: seeking to 1.000 s in mp4/AAC and decoding produced a
     * first output timestamp of 1.0217 s — the decoder consumes the first frame
     * after a seek as priming and never emits it, so ~one frame (23 ms at 44.1
     * kHz) of the requested span simply does not exist in the output. For a
     * replay clip cut at a word boundary that is a clipped onset, audibly.
     * [MediaAudioDecoder.PRE_ROLL_S] exists to make this field's contract true.
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

    /**
     * How far before the requested start to begin decoding.
     *
     * A seek does not put you where you asked. Two effects stack: the extractor
     * lands on the *previous sync sample*, and then the decoder swallows the
     * first frame after a seek as priming — measured on device, mp4/AAC seeked to
     * 1.000 s first emitted output at 1.0217 s, i.e. *after* the request. Without
     * a pre-roll the first ~23 ms of every mid-video span is unrecoverable, and
     * `DecodedAudio.startS` cannot honour its "≤ requested start" contract.
     *
     * 100 ms is ~4 AAC frames and ~5 Opus frames at typical settings, far more
     * than any decoder's priming, and costs 1600 samples of extra decode. The
     * caller trims using `startS`; it must not assume `samples[0]` is the
     * requested instant.
     */
    const val PRE_ROLL_S = 0.1

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
            // Back off by PRE_ROLL_S first: the decoder eats the first frame after
            // a seek, so seeking exactly to `startS` starts the output *after* it.
            // SEEK_TO_PREVIOUS_SYNC, and we keep everything it gives us — see
            // DecodedAudio.startS.
            val from = maxOf(0.0, startS - PRE_ROLL_S)
            extractor.seekTo((from * 1_000_000).toLong(), MediaExtractor.SEEK_TO_PREVIOUS_SYNC)
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
     * Interleaved PCM → mono float32 in [-1, 1], downmixed the way
     * `video.py:extract_audio` does.
     *
     * **Not the average.** This divided by `channels` at first, on the stated
     * belief that averaging is what libswresample's `layout="mono"` downmix does.
     * It is not, and Gate E measured the consequence: our decode of the AAC
     * fixture came out a flat factor of 1.41343 quieter than
     * `ffmpeg -ac 1`'s, and once that single scalar was divided out the two
     * agreed at 49.3 dB — the whole discrepancy was level, not waveform.
     *
     * 1.41343 ≈ √2, which is the giveaway. libswresample rematrixes to preserve
     * *energy*, not amplitude: stereo → mono is `(L+R)/√2`. Measured directly,
     * `ffmpeg -ac 1` maps (0.5, 0.5) → 0.707107, (0.5, 0.0) → 0.353553 and
     * (0.5, −0.5) → 0, all three exactly `(L+R)/√2`.
     *
     * Nothing in today's scoring chain noticed, and that is worth stating
     * precisely rather than treating as luck: `AudioPreproc.frameDb` is
     * `amplitude_to_db(ref=np.max)`, `WordDiff.stressPos` returns the argmax
     * position of an envelope with a relative flatness test, and CMVN normalises
     * every embedding dimension — so a uniform gain cancels in all three, which is
     * why Gate E's DTW cost moved 0.003 and accuracy 0.00. But scale-invariance is
     * a property of the current consumers, not a guarantee: Silero VAD has a
     * trained absolute sensitivity, and anything later that reasons about loudness
     * would silently inherit a 3 dB deficit on video-sourced audio while the
     * AudioRecord learner path — mono, no downmix — stayed correct.
     *
     * Exact for the mono and stereo material `videos/` holds. A true multichannel
     * downmix needs libswresample's per-layout coefficients (centre/LFE
     * weighting); `√ch` is the same energy-preserving principle extended, and is a
     * better approximation than the average, but it is an approximation.
     */
    private fun toMono(buf: java.nio.ByteBuffer, channels: Int, floatPcm: Boolean): FloatArray {
        buf.order(ByteOrder.nativeOrder())
        val ch = if (channels < 1) 1 else channels
        val norm = (1.0 / kotlin.math.sqrt(ch.toDouble())).toFloat()
        return if (floatPcm) {
            val f = buf.asFloatBuffer()
            val n = f.remaining() / ch
            FloatArray(n) { i ->
                var acc = 0.0f
                for (c in 0 until ch) acc += f.get(i * ch + c)
                acc * norm
            }
        } else {
            val s = buf.asShortBuffer()
            val n = s.remaining() / ch
            FloatArray(n) { i ->
                var acc = 0.0f
                for (c in 0 until ch) acc += s.get(i * ch + c) / 32768.0f
                acc * norm
            }
        }
    }
}
