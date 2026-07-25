package com.nativelingo.scoring

import com.nativelingo.scoring.audio.AudioPreproc
import com.nativelingo.scoring.io.NpyReader
import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * `audio_io.py` parity: peak normalisation and `librosa.effects.trim`.
 *
 * Trim boundaries are asserted **exactly**, not within a tolerance. They are
 * integer sample indices, the Python side is deterministic, and they decide both
 * what the DTW sees and FR-8's `learner_offset` — a tolerance here would just be
 * a place for a systematic off-by-one-frame to hide.
 *
 * Fixtures: `golden/audio/` (see `scripts/capture_golden.py:dump_audio_io`).
 */
class AudioPreprocParityTest {

    private fun golden(name: String) =
        javaClass.getResourceAsStream("/golden/audio/$name")
            ?: error("missing golden resource: /golden/audio/$name")

    private fun float1d(name: String): FloatArray {
        val a = NpyReader.read(golden(name))
        return FloatArray(a.size) { a.data[it].toFloat() }
    }

    private fun double1d(name: String): DoubleArray {
        val a = NpyReader.read(golden(name))
        return DoubleArray(a.size) { a.data[it] }
    }

    private fun trimGolden() = TestJson.obj(golden("trim.json").reader().readText())

    @Test
    fun trim_boundaries_match_librosa_exactly_on_every_case() {
        val g = trimGolden()
        assertEquals(AudioPreproc.DEFAULT_TOP_DB, (g["top_db"] as Number).toDouble(), "top_db")
        assertEquals(AudioPreproc.RMS_FRAME, g.int("frame_length"), "frame_length")
        assertEquals(AudioPreproc.RMS_HOP, g.int("hop_length"), "hop_length")

        val cases = g.objList("cases")
        assertTrue(cases.size >= 8, "expected the 5 corpus cases + 3 pads, got ${cases.size}")
        for (c in cases) {
            val name = c.str("name")
            val wav = float1d("${name}_in.npy")
            assertEquals(c.int("n_in"), wav.size, "$name: fixture input length")

            val idx = AudioPreproc.trimIndices(wav)
            assertEquals(c.int("start"), idx[0], "$name: trim start sample")
            assertEquals(c.int("end"), idx[1], "$name: trim end sample")

            val trimmed = AudioPreproc.trimSilence(wav)
            assertEquals(c.int("n_out"), trimmed.size, "$name: trimmed length")

            val r = AudioPreproc.trimSilenceWithOffset(wav)
            assertEquals((c["offset_s"] as Number).toDouble(), r.offsetS, 1e-9, "$name: offset seconds")
            assertEquals(trimmed.size, r.wav.size, "$name: the two entry points must agree")
        }
    }

    @Test
    fun the_threshold_cases_actually_discriminate() {
        // Guards the fixture, not the port: if pad_above and pad_below ever
        // trimmed the same way, the -30dB threshold would be untested and the
        // case above would still pass. A wrong `amin` or `ref` in the dB chain
        // is exactly what this pair is here to catch.
        val cases = trimGolden().objList("cases").associateBy { it.str("name") }
        val above = cases.getValue("pad_above")
        val below = cases.getValue("pad_below")
        assertEquals(0, above.int("start"), "a pad 4dB above the threshold is signal — keep it all")
        assertTrue(below.int("start") > 0, "a pad 4dB below the threshold must be trimmed")
        assertTrue(
            below.int("start") <= below.int("lead_samples"),
            "trim starts at a frame boundary at or before the speech onset, never after it",
        )
    }

    @Test
    fun trim_start_lands_on_a_frame_boundary_before_the_onset() {
        // pad_zero is the real-world case (record-button latency). librosa's
        // centre-padded framing means the first non-silent frame straddles the
        // onset, so the kept region starts *before* it — 4096 for a 4800-sample
        // lead. An implementation that framed without centring would return
        // 4800-ish and still "look right" in a listening test.
        val c = trimGolden().objList("cases").first { it.str("name") == "pad_zero" }
        val start = c.int("start")
        assertEquals(0, start % AudioPreproc.RMS_HOP, "start must be a multiple of the hop")
        assertTrue(start < c.int("lead_samples"), "centre-padded framing keeps audio before the onset")
    }

    @Test
    fun frame_rms_and_db_match_librosa_element_wise() {
        // The stage-by-stage check: if trim boundaries drift, this says whether
        // the framing, the RMS, or the dB conversion is at fault.
        val wav = float1d("pad_zero_in.npy")
        val rms = AudioPreproc.frameRms(wav)
        val goldRms = double1d("pad_zero_rms.npy")
        assertEquals(goldRms.size, rms.size, "frame count")

        var maxRmsErr = 0.0
        for (i in rms.indices) maxRmsErr = maxOf(maxRmsErr, abs(rms[i] - goldRms[i]))
        assertTrue(maxRmsErr < 1e-6, "frame RMS max-diff $maxRmsErr (need < 1e-6)")

        val db = AudioPreproc.frameDb(rms)
        val goldDb = double1d("pad_zero_db.npy")
        assertEquals(goldDb.size, db.size, "dB frame count")
        var maxDbErr = 0.0
        for (i in db.indices) maxDbErr = maxOf(maxDbErr, abs(db[i] - goldDb[i]))
        assertTrue(maxDbErr < 1e-3, "frame dB max-diff $maxDbErr (need < 1e-3)")

        // The amin clamp: silent frames land on a flat finite floor instead of
        // -Inf. Not -100dB — dB is relative to the loudest frame, so the floor
        // sits at -100 minus the reference term (~-88.9 here).
        var maxRms = 0.0
        for (v in rms) maxRms = maxOf(maxRms, v)
        val expectedFloor = -100.0 - 10.0 * kotlin.math.log10(maxOf(1e-10, maxRms * maxRms))
        assertTrue(db.all { it.isFinite() }, "no frame may be -Inf or NaN")
        assertEquals(expectedFloor, db.min(), 1e-6, "the zero pad must sit exactly on the amin floor")
        assertTrue(expectedFloor < -AudioPreproc.DEFAULT_TOP_DB, "the floor must be below the threshold")
        assertEquals(0.0, db.max(), 1e-9, "the loudest frame is 0dB by construction")
    }

    @Test
    fun peak_normalisation_matches_and_leaves_near_silence_alone() {
        for (c in trimGolden().objList("normalize")) {
            val label = c.str("label")
            val input = float1d("norm_${label}_in.npy")
            val gold = float1d("norm_${label}_out.npy")
            val mine = AudioPreproc.normalize(input)
            assertEquals(gold.size, mine.size, "$label: length")
            var maxErr = 0.0
            for (i in mine.indices) maxErr = maxOf(maxErr, abs(mine[i].toDouble() - gold[i].toDouble()))
            assertTrue(maxErr < 1e-7, "$label: normalise max-diff $maxErr")

            val scaled = c["scaled"] as Boolean
            if (!scaled) {
                assertTrue(input.contentEquals(mine), "$label: must be returned untouched")
            }
        }
        // and state the invariant the fixture encodes, so it can't be lost in a regen
        val labels = trimGolden().objList("normalize").associateBy { it.str("label") }
        assertFalse(labels.getValue("near_silent")["scaled"] as Boolean,
            "a peak <= 1e-6 take must not be amplified to full scale")
        assertTrue(labels.getValue("quiet")["scaled"] as Boolean, "a quiet but real take is normalised")
    }

    @Test
    fun degenerate_inputs_do_not_throw() {
        val empty = FloatArray(0)
        assertEquals(0, AudioPreproc.trimSilence(empty).size)
        assertEquals(0.0, AudioPreproc.trimSilenceWithOffset(empty).offsetS)
        assertEquals(0, AudioPreproc.normalize(empty).size)

        // All-silent is kept WHOLE, which is not the intuitive answer: dB is
        // relative to the loudest frame, so silence-vs-silence ties at 0dB and
        // counts as signal. Checked against librosa 0.11 (`trim(zeros(8000))`
        // returns [0, 8000]); a dead take therefore reaches the encoder at full
        // length and scores badly rather than vanishing.
        val silence = FloatArray(8000)
        assertTrue(AudioPreproc.trimIndices(silence).contentEquals(intArrayOf(0, 8000)),
            "all-silent input is not trimmed — see librosa's relative-dB reference")
        assertEquals(silence.size, AudioPreproc.trimSilence(silence).size)
        assertEquals(0.0, AudioPreproc.trimSilenceWithOffset(silence).offsetS)

        // NaN is the path that actually reaches [0, 0] (every comparison against
        // NaN is false), and trim_silence must hand back the original rather
        // than an empty array — an empty waveform crashes the encoder downstream
        // instead of scoring as a bad take.
        val broken = FloatArray(8000) { if (it == 4000) Float.NaN else 0.3f }
        assertTrue(AudioPreproc.trimIndices(broken).contentEquals(intArrayOf(0, 0)),
            "a NaN anywhere makes every dB comparison false")
        assertEquals(broken.size, AudioPreproc.trimSilence(broken).size, "fall back to the original")
        assertEquals(0.0, AudioPreproc.trimSilenceWithOffset(broken).offsetS)

        // shorter than one frame — the centre padding is what makes this legal
        val tiny = FloatArray(100) { 0.5f }
        assertTrue(AudioPreproc.frameRms(tiny).isNotEmpty(), "a sub-frame signal still yields frames")
        assertEquals(tiny.size, AudioPreproc.trimSilence(tiny).size)
    }
}
