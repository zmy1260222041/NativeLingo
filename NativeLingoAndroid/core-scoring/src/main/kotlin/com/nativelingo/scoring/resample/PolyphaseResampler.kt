package com.nativelingo.scoring.resample

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Rational-factor resampling by polyphase FIR filtering — a 1:1 port of
 * `scipy.signal.resample_poly(x, up, down)` with its default Kaiser(5.0) design.
 *
 * ### Why this exists, and why it is in `:core-scoring`
 *
 * On Android the *reference* audio arrives from `MediaCodec` at the container's
 * native rate (44.1/48 kHz) and has to be brought to 16 kHz in-process; the
 * *learner's* never does, because `AudioRecord` captures at 16 kHz directly.
 * macOS resamples with libswresample (`video.py`) — and, inconsistently, with
 * soxr elsewhere (`audio_io.py`).
 *
 * R-9 measured what that inconsistency is worth. Against libswresample, this
 * filter differs by only 30–43 dB SNR at the sample level (hundreds of int16
 * LSBs — the original Gate E criterion of "≤1 LSB" is unreachable by
 * construction once the kernel changes), yet the CMVN'd per-frame embedding
 * cosine stays at 0.9983–0.9998 and swapping the reference's resampler moves
 * the DTW cost by ≤0.0011 and the calibrated accuracy by 0.00 — 18× inside the
 * Gate A tolerance. So the resampled samples feed a score, which is the module
 * invariant's trigger: this belongs here, in pure Kotlin, testable on the JVM.
 * See `docs/reviews/2026-07-26-android-gate-e-audio-decode.md`.
 *
 * ### Why match scipy exactly rather than "any good resampler"
 *
 * Because that is the one measured above. Tracking a specific, independently
 * implemented reference turns an open-ended question ("is our filter good
 * enough?") into a closed one the golden fixture can answer.
 *
 * ### The design, verbatim from scipy
 *
 * With `g = gcd(up, down)` removed, `maxRate = max(up, down)`:
 *  - `halfLen = 10 * maxRate`, `numtaps = 2 * halfLen + 1`
 *  - lowpass at `1 / maxRate` of Nyquist, Kaiser(β=5.0) window
 *  - normalised to unit DC gain, then multiplied by `up`
 *  - zero-padded in front by `down - halfLen % down` so the output samples land
 *    centred, then the first `(halfLen + prePad) / down` outputs are dropped
 *
 * Note `up = 1, down = 3` (48 kHz → 16 kHz) yields a 61-tap filter while
 * `up = 160, down = 441` (44.1 kHz) yields 8821. That asymmetry is scipy's, and
 * it is kept: the point is the port, not an improvement on it.
 */
object PolyphaseResampler {

    const val KAISER_BETA = 5.0

    /** Resample `x` from `srIn` to `srOut`; returns `x` itself when equal. */
    fun resample(x: FloatArray, srIn: Int, srOut: Int): FloatArray {
        if (srIn == srOut) return x
        val g = gcd(srIn, srOut)
        return resampleRatio(x, up = srOut / g, down = srIn / g)
    }

    fun resampleRatio(x: FloatArray, up: Int, down: Int): FloatArray {
        val d = resampleRatio(DoubleArray(x.size) { x[it].toDouble() }, up, down)
        return FloatArray(d.size) { d[it].toFloat() }
    }

    fun resample(x: DoubleArray, srIn: Int, srOut: Int): DoubleArray {
        if (srIn == srOut) return x
        val g = gcd(srIn, srOut)
        return resampleRatio(x, up = srOut / g, down = srIn / g)
    }

    /**
     * The core. `up`/`down` need not be coprime — the gcd is removed here, as
     * scipy does. Note the argument *order* differs from [resample]:
     * `resample(x, srIn = 44100, srOut = 16000)` is `resampleRatio(x, 160, 441)`.
     */
    fun resampleRatio(x: DoubleArray, up: Int, down: Int): DoubleArray {
        require(up > 0 && down > 0) { "up/down must be positive, got up=$up down=$down" }
        val g = gcd(up, down)
        val u = up / g
        val dn = down / g
        if (u == 1 && dn == 1) return x.copyOf()
        val nIn = x.size
        if (nIn == 0) return DoubleArray(0)

        val nOutLong = nIn.toLong() * u
        val nOut = (nOutLong / dn + if (nOutLong % dn != 0L) 1 else 0).toInt()

        val maxRate = max(u, dn)
        val halfLen = 10 * maxRate
        val h = designFilter(numtaps = 2 * halfLen + 1, cutoff = 1.0 / maxRate)
        for (i in h.indices) h[i] *= u

        // Front-pad so the output is centred on the filter's group delay, then
        // drop the samples that padding introduced. `prePad` is `down` (not 0)
        // when `halfLen` divides `down` — scipy's expression, kept literally.
        val prePad = dn - halfLen % dn
        val preRemove = (halfLen + prePad) / dn
        var postPad = 0
        while (upfirdnLen(h.size + prePad + postPad, nIn, u, dn) < nOut + preRemove) postPad++

        val hp = DoubleArray(prePad + h.size + postPad)
        h.copyInto(hp, prePad)

        // y[i] = sum_j hp[j] * xUp[pos - j], pos = (preRemove + i) * down, where
        // xUp is x zero-stuffed by `up`. Only j ≡ pos (mod up) contributes, so
        // step by `up` from `pos % up` instead of materialising xUp.
        val out = DoubleArray(nOut)
        val lastIn = nIn - 1
        for (i in 0 until nOut) {
            val pos = (preRemove + i).toLong() * dn
            var j = (pos % u).toInt()
            // Skip the taps that would read past the start of x (index > lastIn).
            val minJ = pos - lastIn.toLong() * u
            if (j < minJ) {
                val steps = (minJ - j + u - 1) / u
                j += (steps * u).toInt()
            }
            val jMax = min((hp.size - 1).toLong(), pos).toInt()
            var acc = 0.0
            while (j <= jMax) {
                acc += hp[j] * x[((pos - j) / u).toInt()]
                j += u
            }
            out[i] = acc
        }
        return out
    }

    /** Output length of `upfirdn` — scipy's `_output_len`. */
    private fun upfirdnLen(lenH: Int, nIn: Int, up: Int, down: Int): Long =
        ((nIn - 1).toLong() * up + lenH - 1) / down + 1

    /**
     * `scipy.signal.firwin(numtaps, cutoff, window=('kaiser', beta))` for the
     * single-band lowpass case: `pass_zero=True`, `scale=True`, `fs=2`.
     */
    internal fun designFilter(
        numtaps: Int,
        cutoff: Double,
        beta: Double = KAISER_BETA,
    ): DoubleArray {
        val alpha = 0.5 * (numtaps - 1)
        val win = kaiser(numtaps, beta)
        val h = DoubleArray(numtaps)
        var sum = 0.0
        for (i in 0 until numtaps) {
            val m = i - alpha
            h[i] = cutoff * sinc(cutoff * m) * win[i]
            sum += h[i]                     // scale at DC: cos(pi*m*0) == 1
        }
        for (i in 0 until numtaps) h[i] /= sum
        return h
    }

    /** `numpy.sinc`: sin(pi x) / (pi x), 1 at x = 0. */
    private fun sinc(x: Double): Double {
        if (x == 0.0) return 1.0
        val px = PI * x
        return sin(px) / px
    }

    /** `numpy.kaiser(m, beta)` — symmetric, length `m`. */
    internal fun kaiser(m: Int, beta: Double): DoubleArray {
        if (m == 1) return doubleArrayOf(1.0)
        val alpha = (m - 1) / 2.0
        val denom = besselI0(beta)
        return DoubleArray(m) { n ->
            val t = (n - alpha) / alpha
            besselI0(beta * sqrt(max(0.0, 1.0 - t * t))) / denom
        }
    }

    /**
     * Modified Bessel function of the first kind, order 0, by its power series
     * `sum (x²/4)^k / (k!)²`. Converges to machine precision within ~20 terms
     * for the arguments a Kaiser window uses (|x| ≤ β = 5); a polynomial
     * approximation would cap the port's agreement with scipy at ~1e-7 for no
     * reason, and the whole point here is to be exact.
     */
    internal fun besselI0(x: Double): Double {
        val t = 0.25 * x * x
        var term = 1.0
        var sum = 1.0
        var k = 1
        while (k < 64) {
            term *= t / (k.toDouble() * k)
            sum += term
            if (term < 1e-18 * abs(sum)) break
            k++
        }
        return sum
    }

    private tailrec fun gcd(a: Int, b: Int): Int = if (b == 0) a else gcd(b, a % b)
}
