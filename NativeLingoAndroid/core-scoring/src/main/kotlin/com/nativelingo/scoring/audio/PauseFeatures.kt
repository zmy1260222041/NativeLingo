package com.nativelingo.scoring.audio

/**
 * Port of `backend/core/prosody.py`'s pause path — `extract_prosody` →
 * `_count_pauses` — reduced to the two features the calibrated fluency GAM
 * actually consumes.
 *
 * Why only pauses, and why this is not Praat:
 *  - macOS `extract_prosody` uses Praat `to_intensity()` for pause detection
 *    *and* Parselmouth for F0 (intonation). F0 has no bit-exact JVM twin on
 *    Android — TarsosDSP YIN is the planned substitute, the same equivalence
 *    gap as FR-7 pitch — so the intonation features (`f0_std`, and the
 *    `intonation_match` derived from them) are deferred. They do not enter the
 *    fluency score anyway.
 *  - `scoreTrackB`'s fluency GAM (`calibration.json`) uses **only
 *    `pause_ratio`**; `pause_per_s` is an API-stability placeholder that the
 *    GAM ignores (`score_b.py:78`). So the one thing `AnalyzePipeline` needs
 *    from this module to score fluency is the pause detection.
 *  - Praat `to_intensity()` has no Android equivalent. This detector reuses
 *    `AudioPreproc.frameRms` / `frameDb` — the same power-domain dB chain that
 *    already reproduces `librosa.effects.trim` bit-for-bit — with Praat's
 *    threshold (`-25 dB` relative to the loudest frame) and minimum pause
 *    (`0.15 s`). On the JVM golden set the four macOS-`say` clips are
 *    pause-free (Praat measured 0), so RMS agrees exactly. On real
 *    pause-bearing learner audio the two detectors can disagree at the
 *    boundaries; that bounded divergence is a *device-side* fluency-parity
 *    item, tracked alongside the TarsosDSP pitch gap — not a JVM-golden one.
 *
 * Why the framing here is finer than the trim chain's:
 *  - `AudioPreproc.trimIndices` must keep `librosa`'s 2048/512 framing to match
 *    macOS sample-for-sample. But a 2048-sample frame is 128 ms — too coarse to
 *    resolve Praat's 0.15 s minimum pause (it would be barely one frame wide).
 *    Pause detection therefore uses its own 30 ms / 10 ms framing so the floor
 *    is meaningful. The two chains serve different contracts and need not share
 *    a window.
 *
 * Lives in `:core-scoring` (pure JVM) because `pause_ratio` shapes the calibrated
 * fluency score — the module invariant (docs/android-migration.md §8) applies.
 */
object PauseFeatures {

    /** Praat `extract_prosody`'s `silence_db = -25.0`: a frame is silent when its dB is ≥25 below the max. */
    const val SILENCE_DB = 25.0

    /** Praat `extract_prosody`'s `min_pause_s = 0.15`: silent runs shorter than this are not pauses. */
    const val MIN_PAUSE_S = 0.15

    /**
     * Framing for pause detection: 30 ms window, 10 ms hop. Gives 10 ms
     * resolution so the 0.15 s floor spans ~15 frames rather than ~1.
     * Independent of [AudioPreproc.RMS_FRAME] / [AudioPreproc.RMS_HOP].
     */
    const val PAUSE_FRAME = 480
    const val PAUSE_HOP = 160

    /** What `extract_prosody` returns that this port keeps (drops F0 / articulation rate). */
    data class Features(val durationS: Double, val numPauses: Int, val totalPauseS: Double)

    /**
     * `(pauses/sec, pause-time-ratio)` — exactly what `pipeline._pause_feats`
     * returns and `scoreTrackB` consumes. The `max(duration, 1e-3)` guard is
     * Praat's, so a zero-length take does not divide by zero.
     */
    fun fluencyInputs(wav: FloatArray, sr: Int = AudioPreproc.TARGET_SR): Pair<Double, Double> {
        val f = extract(wav, sr)
        val dur = maxOf(f.durationS, 1e-3)
        return f.numPauses / dur to f.totalPauseS / dur
    }

    /**
     * Detect silent pauses. Mirrors `extract_prosody`'s pause branch: per-frame
     * dB relative to the loudest frame, a frame is silent when its level is
     * ≥ [silenceDb] below the max, and a run of silent frames ≥ [minPauseS]
     * long counts as one pause.
     */
    fun extract(
        wav: FloatArray,
        sr: Int = AudioPreproc.TARGET_SR,
        silenceDb: Double = SILENCE_DB,
        minPauseS: Double = MIN_PAUSE_S,
    ): Features {
        if (wav.isEmpty()) return Features(0.0, 0, 0.0)
        val duration = wav.size.toDouble() / sr
        val db = AudioPreproc.frameDb(AudioPreproc.frameRms(wav, PAUSE_FRAME, PAUSE_HOP))
        // Praat: `silent = vals < (nanmax(vals) + silence_db)`. frameDb is already
        // relative to the max frame (max == 0 dB), so the threshold is -silenceDb.
        val (num, total) = countPauses(DoubleArray(db.size) { if (db[it] < -silenceDb) 1.0 else 0.0 },
            PAUSE_HOP.toDouble() / sr, minPauseS)
        return Features(duration, num, total)
    }

    /**
     * Port of `prosody._count_pauses`: count runs of consecutive silent frames
     * whose duration ≥ [minPauseS]. [dt] is seconds per frame.
     *
     * Implemented over a silent-mask callback rather than Praat's `(times, mask)`
     * pair because the framing is fixed here; the algorithm is identical.
     */
    private fun countPauses(silent: DoubleArray, dt: Double, minPauseS: Double): Pair<Int, Double> {
        if (silent.size < 2) return 0 to 0.0
        var num = 0
        var total = 0.0
        var run = 0
        for (s in silent) {
            if (s > 0.0) {
                run++
            } else {
                val dur = run * dt
                if (dur >= minPauseS) { num++; total += dur }
                run = 0
            }
        }
        val dur = run * dt
        if (dur >= minPauseS) { num++; total += dur }
        return num to total
    }
}
