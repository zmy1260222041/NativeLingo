package com.nativelingo.app.gates

import com.nativelingo.scoring.norm.cmvn
import kotlin.math.abs
import kotlin.math.log10
import kotlin.math.min
import kotlin.math.sqrt

/**
 * The comparisons the gate criteria are stated in.
 *
 * Deliberately duplicated from the JVM tests rather than shared: these are the
 * *measuring instrument*, and the point of a device gate is to compare device
 * numbers against the macOS goldens using the same instrument the desktop
 * reviews used. Pulling them out into a shared fixture would make it possible
 * for a change to the instrument to move both sides together and hide a drift.
 */
object Numeric {

    /** Frame-wise cosine after CMVN — the Layer-2 criterion (≥0.995). */
    fun cosAfterCmvn(a: Array<FloatArray>, b: Array<FloatArray>): Double {
        val n = min(a.size, b.size)
        require(n > 0) { "empty embedding" }
        val an = cmvn(a.sliceArray(0 until n))
        val bn = cmvn(b.sliceArray(0 until n))
        var dot = 0.0
        var na = 0.0
        var nb = 0.0
        for (t in 0 until n) for (d in an[t].indices) {
            dot += an[t][d] * bn[t][d]
            na += an[t][d] * an[t][d]
            nb += bn[t][d] * bn[t][d]
        }
        return dot / (sqrt(na) * sqrt(nb) + 1e-12)
    }

    /**
     * Frame-wise cosine with no normalization — for emissions.
     *
     * CMVN must NOT be applied here. Emissions are log-probabilities, where the
     * absolute level carries meaning (the Viterbi sums them, and FR-11's gates
     * compare the sums against fixed thresholds of 0.05/0.15). Centring them per
     * dimension would discard exactly the part int8 is most likely to shift.
     */
    fun cosRaw(a: Array<FloatArray>, b: Array<FloatArray>): Double {
        val n = min(a.size, b.size)
        require(n > 0) { "empty emission" }
        var dot = 0.0
        var na = 0.0
        var nb = 0.0
        for (t in 0 until n) for (d in a[t].indices) {
            dot += a[t][d].toDouble() * b[t][d]
            na += a[t][d].toDouble() * a[t][d]
            nb += b[t][d].toDouble() * b[t][d]
        }
        return dot / (sqrt(na) * sqrt(nb) + 1e-12)
    }

    /** Signal-to-noise ratio in dB of [got] against [want], over the overlap. */
    fun snrDb(want: FloatArray, got: FloatArray): Double {
        val n = min(want.size, got.size)
        var sig = 0.0
        var err = 0.0
        for (i in 0 until n) {
            val w = want[i].toDouble()
            val d = w - got[i].toDouble()
            sig += w * w
            err += d * d
        }
        if (err == 0.0) return Double.POSITIVE_INFINITY
        return 10.0 * log10(sig / err)
    }

    /**
     * The single scale factor that best maps [got] onto [want], and the SNR left
     * once it is applied: `least-squares g = <want,got>/<got,got>`.
     *
     * Separating gain from waveform error is not cosmetic here. A decoder that
     * differs from the reference only by a constant level — MPEG-4 DRC / loudness
     * normalisation is applied by some AAC decoders and not others — produces a
     * terrible sample-domain SNR and yet changes nothing downstream, because CMVN
     * normalises each embedding dimension before the DTW ever sees it. A decoder
     * that differs in *shape* is a different matter. Reporting only SNR cannot
     * tell those two apart, and they have opposite consequences.
     */
    fun bestGain(want: FloatArray, got: FloatArray): Pair<Double, Double> {
        val n = min(want.size, got.size)
        var wg = 0.0
        var gg = 0.0
        for (i in 0 until n) {
            wg += want[i].toDouble() * got[i]
            gg += got[i].toDouble() * got[i]
        }
        val g = if (gg > 1e-20) wg / gg else 1.0
        val scaled = FloatArray(n) { (got[it] * g).toFloat() }
        return g to snrDb(want.copyOfRange(0, n), scaled)
    }

    fun maxAbsDiff(want: FloatArray, got: FloatArray): Double {
        var m = 0.0
        for (i in 0 until min(want.size, got.size)) {
            m = maxOf(m, abs(want[i].toDouble() - got[i].toDouble()))
        }
        return m
    }

    /**
     * The integer sample lag that best aligns [got] to [want].
     *
     * Needed because a container round-trip is not sample-aligned: AAC carries an
     * encoder delay (~2112 samples at the encode rate) and different decoders
     * account for it differently — ffmpeg trims it using the container's edit
     * list, MediaCodec's behaviour depends on the OEM. That offset is not an
     * error in either decoder, but comparing across it would report a total
     * mismatch, and at a 320-sample frame stride even a 700-sample offset is two
     * whole embedding frames.
     *
     * Correlation peak over `±maxLag`, restricted to the first [probe] samples so
     * this stays cheap on a low-end device.
     */
    fun bestLag(want: FloatArray, got: FloatArray, maxLag: Int = 4000, probe: Int = 16_000): Int {
        var bestLag = 0
        var best = -Double.MAX_VALUE
        for (lag in -maxLag..maxLag) {
            var dot = 0.0
            var eg = 0.0
            var n = 0
            var i = maxOf(0, -lag)
            val end = min(probe, min(want.size, got.size - lag))
            while (i < end) {
                val g = got[i + lag].toDouble()
                dot += want[i].toDouble() * g
                eg += g * g
                n++
                i++
            }
            if (n < probe / 2) continue
            val score = dot / (sqrt(eg) + 1e-12)
            if (score > best) {
                best = score
                bestLag = lag
            }
        }
        return bestLag
    }

    /**
     * [got] delayed by a *fractional* number of samples, by windowed-sinc
     * interpolation. `out[n] ≈ got[n + delta]`.
     *
     * Integer alignment is not enough for Gate E, and the reason is arithmetic.
     * FFmpeg trims AAC's encoder priming — 2112 samples at 44.1 kHz — using the
     * container's edit list, *before* resampling. 2112 · 16000/44100 = 766.2
     * samples: the trim is a whole number of input samples and a fractional
     * number of output ones, so the two paths' 16 kHz grids are offset by a
     * fraction of a sample no integer shift can remove.
     *
     * That fraction is not small in the sample domain. A shift of δ samples costs
     * a component at frequency f roughly `2·sin(πfδ/fs)` in amplitude, so 0.2
     * samples at 3 kHz is already about -12 dB — which is why the first version of
     * these tests measured 10.7 dB SNR between two AAC decoders that should agree
     * to 60 dB, and read a pure timing offset as decoder infidelity.
     */
    fun shiftBy(got: FloatArray, delta: Double, taps: Int = 24): FloatArray {
        val i0 = kotlin.math.floor(delta).toInt()
        val frac = delta - i0
        val out = FloatArray(got.size)
        for (n in out.indices) {
            var acc = 0.0
            var wsum = 0.0
            for (k in -taps + 1..taps) {
                val src = n + i0 + k
                if (src < 0 || src >= got.size) continue
                val t = k - frac
                // Windowed sinc: Hann over the 2·taps span keeps the kernel short
                // without ringing. Renormalised by the window sum so a truncated
                // kernel near the edges does not change the signal's level.
                val sinc = if (abs(t) < 1e-9) 1.0
                    else kotlin.math.sin(Math.PI * t) / (Math.PI * t)
                val w = 0.5 * (1.0 + kotlin.math.cos(Math.PI * t / taps))
                val h = sinc * w
                acc += got[src] * h
                wsum += h
            }
            out[n] = (if (abs(wsum) > 1e-9) acc / wsum else acc).toFloat()
        }
        return out
    }

    /**
     * The fractional lag that best aligns [got] to [want], refining [coarse].
     *
     * Brute force over a fine grid rather than parabolic interpolation of the
     * correlation peak: the grid costs milliseconds here and cannot be subtly
     * wrong, and this is the measuring instrument for a gate.
     */
    fun bestFractionalLag(
        want: FloatArray,
        got: FloatArray,
        coarse: Int,
        range: Double = 1.0,
        step: Double = 0.02,
    ): Double {
        var best = coarse.toDouble()
        var bestSnr = -Double.MAX_VALUE
        var d = coarse - range
        while (d <= coarse + range + 1e-9) {
            val snr = snrDb(want, shiftBy(got, d))
            if (snr > bestSnr) { bestSnr = snr; best = d }
            d += step
        }
        return best
    }

    /** [got] shifted by [lag] and both trimmed to a common length. */
    fun alignTo(want: FloatArray, got: FloatArray, lag: Int): Pair<FloatArray, FloatArray> {
        val wStart = maxOf(0, -lag)
        val gStart = maxOf(0, lag)
        val n = min(want.size - wStart, got.size - gStart)
        require(n > 0) { "no overlap at lag $lag" }
        return want.copyOfRange(wStart, wStart + n) to got.copyOfRange(gStart, gStart + n)
    }
}
