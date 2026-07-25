package com.nativelingo.scoring.audio

import kotlin.math.abs
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.sqrt

/**
 * Port of `backend/core/audio_io.py` — peak normalisation and silence trimming.
 *
 * This lives in `:core-scoring` rather than `:core-audio` on purpose. The module
 * invariant (docs/android-migration.md §8) is that anything affecting a
 * calibrated score stays pure-JVM and golden-testable without a device, and trim
 * is squarely that: it decides which samples reach the DTW, and its leading
 * offset is what FR-8 adds back when replaying the learner's own take. Only
 * decoding and file I/O — the parts that genuinely need the NDK — belong in
 * `:core-audio`.
 *
 * [trimIndices] reproduces `librosa.effects.trim` (librosa 0.11) exactly, chain
 * and all, because "trim leading silence" has many reasonable implementations
 * that disagree by a few hundred samples and macOS's answer is the contract.
 * Golden fixtures: `golden/audio/trim.json` (per-case `[start, end]`).
 */
object AudioPreproc {

    const val TARGET_SR = 16000

    /** `trim_silence`'s default. Not librosa's default (60) — audio_io overrides it. */
    const val DEFAULT_TOP_DB = 30.0

    /** `librosa.feature.rms` defaults, reached via `_signal_to_frame_nonsilent`. */
    const val RMS_FRAME = 2048
    const val RMS_HOP = 512

    /**
     * `librosa.amplitude_to_db(amin=1e-5)` squared, since the amplitude form
     * forwards `amin**2` to `power_to_db`. Clamping in the power domain is why
     * digital silence lands at exactly -100 dB instead of -infinity.
     */
    private const val AMIN_POWER = 1e-10

    /** Below this peak, `_normalize` leaves the signal alone (see [normalize]). */
    private const val PEAK_FLOOR = 1e-6

    /** Peak-normalise to +-1. Mirrors `audio_io._normalize`. */
    fun normalize(wav: FloatArray): FloatArray {
        var peak = 0.0f
        for (v in wav) {
            val a = abs(v)
            if (a > peak) peak = a
        }
        // A near-silent take is left untouched rather than divided by its own
        // noise floor — otherwise a failed recording gets amplified to full
        // scale and then scored as if it were speech.
        if (peak <= PEAK_FLOOR) return wav.copyOf()
        return FloatArray(wav.size) { wav[it] / peak }
    }

    /**
     * Per-frame RMS, matching `librosa.feature.rms(center=true, pad_mode="constant")`:
     * zero-pad by `frameLength / 2` on both ends, then frame with `hopLength`.
     *
     * Accumulated in Double where numpy stays in float32 (its `mean` keeps the
     * input's precision). Measured relative difference is ~4e-8 — far below the
     * dB margins any trim decision turns on, and in the safe direction.
     */
    fun frameRms(wav: FloatArray, frameLength: Int = RMS_FRAME, hopLength: Int = RMS_HOP): DoubleArray {
        require(frameLength > 0 && hopLength > 0) { "frameLength/hopLength must be positive" }
        val pad = frameLength / 2
        val padded = wav.size + 2 * pad
        val nFrames = (padded - frameLength) / hopLength + 1
        if (nFrames <= 0) return DoubleArray(0)

        val out = DoubleArray(nFrames)
        for (i in 0 until nFrames) {
            val base = i * hopLength - pad   // index into the *unpadded* signal
            var acc = 0.0
            for (j in 0 until frameLength) {
                val k = base + j
                if (k < 0 || k >= wav.size) continue   // the zero padding
                val v = wav[k].toDouble()
                acc += v * v
            }
            out[i] = sqrt(acc / frameLength)
        }
        return out
    }

    /**
     * `amplitude_to_db(rms, ref=np.max, top_db=None)`: relative to the loudest
     * frame, in the power domain, floored at [AMIN_POWER].
     */
    fun frameDb(rms: DoubleArray): DoubleArray {
        if (rms.isEmpty()) return DoubleArray(0)
        var refAmp = 0.0
        for (v in rms) refAmp = max(refAmp, abs(v))
        val refTerm = 10.0 * log10(max(AMIN_POWER, refAmp * refAmp))
        return DoubleArray(rms.size) { 10.0 * log10(max(AMIN_POWER, rms[it] * rms[it])) - refTerm }
    }

    /**
     * `librosa.effects.trim`'s returned index pair: `[start, end)` in samples.
     *
     * Note what this does **not** do: an all-silent take is kept whole, not
     * reduced to nothing. dB here is relative to the loudest frame, so when the
     * loudest frame is itself silence every frame ties at 0 dB and counts as
     * signal. Verified against librosa 0.11 rather than assumed — a dead take
     * reaches the encoder at full length and scores badly, which is the
     * behaviour macOS already has.
     *
     * The `[0, 0]` return is therefore not the silence path; it is the NaN path
     * (every comparison against NaN is false), which a broken decode can reach.
     * [trimSilence] turns it back into the untrimmed signal.
     */
    fun trimIndices(
        wav: FloatArray,
        topDb: Double = DEFAULT_TOP_DB,
        frameLength: Int = RMS_FRAME,
        hopLength: Int = RMS_HOP,
    ): IntArray {
        if (wav.isEmpty()) return intArrayOf(0, 0)
        val db = frameDb(frameRms(wav, frameLength, hopLength))
        var first = -1
        var last = -1
        for (i in db.indices) {
            if (db[i] > -topDb) {
                if (first < 0) first = i
                last = i
            }
        }
        if (first < 0) return intArrayOf(0, 0)
        // frames_to_samples with no n_fft: the centre-padding is already baked
        // into the framing, so a frame index maps straight to frame * hop.
        val start = first * hopLength
        val end = minOf(wav.size, (last + 1) * hopLength)
        return intArrayOf(start, end)
    }

    /** `trim_silence`: trimmed signal, or the original if trimming left nothing. */
    fun trimSilence(wav: FloatArray, topDb: Double = DEFAULT_TOP_DB): FloatArray {
        if (wav.isEmpty()) return wav
        val (start, end) = trimIndices(wav, topDb)
        if (end <= start) return wav
        return wav.copyOfRange(start, end)
    }

    /**
     * `trim_silence_with_offset`: also returns the leading silence removed, in
     * seconds. FR-8 adds this back to map trimmed-relative sentence times onto
     * the learner's original upload.
     */
    fun trimSilenceWithOffset(
        wav: FloatArray,
        topDb: Double = DEFAULT_TOP_DB,
        sr: Int = TARGET_SR,
    ): TrimResult {
        if (wav.isEmpty()) return TrimResult(wav, 0.0)
        val (start, end) = trimIndices(wav, topDb)
        if (end <= start) return TrimResult(wav, 0.0)
        return TrimResult(wav.copyOfRange(start, end), start.toDouble() / sr)
    }
}

/** [AudioPreproc.trimSilenceWithOffset]'s result: the trimmed audio and the seconds dropped from the front. */
class TrimResult(val wav: FloatArray, val offsetS: Double)
