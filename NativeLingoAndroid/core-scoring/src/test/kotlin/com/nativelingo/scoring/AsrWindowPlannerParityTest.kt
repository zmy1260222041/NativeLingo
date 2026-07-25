package com.nativelingo.scoring

import com.nativelingo.scoring.segment.AsrWindowPlanner
import com.nativelingo.scoring.segment.AsrWindowPlanner.Span
import com.nativelingo.scoring.segment.SentenceSegmenter
import com.nativelingo.scoring.segment.TimedWord
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * ASR windowing parity (R-10 / Gate F, FR-2 + FR-M3).
 *
 * The recognizer itself cannot run here — it is an Android AAR — so what is
 * pinned is the part that decides *where the cuts go*, which is the part R-10
 * showed to dominate transcript quality. The fixture records the 77 VAD spans
 * of a real 636 s clip and the 27 windows the measured Python run derived from
 * them; Kotlin must derive the same 27.
 *
 * Fixture: `golden/asr/vadwin_trace.json` (see `scripts/asr_text_parity.py`).
 */
class AsrWindowPlannerParityTest {

    private val g by lazy {
        TestJson.obj(
            javaClass.getResourceAsStream("/golden/asr/vadwin_trace.json")!!
                .reader().readText()
        )
    }

    @Suppress("UNCHECKED_CAST")
    private val spans: List<Span> by lazy {
        (g["vad_spans"] as List<Any?>).map {
            val p = it as List<Any?>
            Span((p[0] as Number).toInt(), (p[1] as Number).toInt())
        }
    }

    @Test
    fun windows_match_the_measured_python_run() {
        val expected = g.objList("windows")
        val winS = (g["win_s"] as Number).toDouble()
        val got = AsrWindowPlanner.plan(spans, (winS * g.int("sample_rate")).toInt())
        assertEquals(expected.size, got.size, "window count")
        for (i in expected.indices) {
            val e = expected[i]
            assertEquals(e.int("first_span"), got[i].firstSpan, "window[$i].firstSpan")
            assertEquals(e.int("last_span"), got[i].lastSpan, "window[$i].lastSpan")
            assertEquals(e.int("start"), got[i].start, "window[$i].start")
            assertEquals(e.int("end"), got[i].end, "window[$i].end")
        }
    }

    @Test
    fun the_fixture_is_the_case_that_makes_merging_worth_it() {
        // Guards the fixture, not the port: if the corpus ever stopped needing
        // merging (one span per window), the test above would still pass while
        // testing nothing. 77 spans collapsing to 27 windows is the property.
        assertEquals(77, spans.size, "fixture VAD span count")
        val windows = AsrWindowPlanner.plan(spans)
        assertEquals(27, windows.size, "fixture window count")
        assertTrue(windows.count { it.lastSpan > it.firstSpan } >= 15,
            "most windows should actually merge several spans")
    }

    @Test
    fun only_a_lone_oversized_vad_span_can_break_the_cap_and_two_do() {
        // Not the tidy invariant it looks like it should be. Silero is asked for
        // max_speech_duration = 25 s and sherpa-onnx treats that as a hint: two
        // spans come back at 29.91 s and 30.17 s. Merging can never create an
        // over-long window (the bound is checked against the window start), so
        // every violation is a single span passed straight through.
        val win = AsrWindowPlanner.windowSamples()
        assertEquals(464_000, win, "29 s at 16 kHz")
        val windows = AsrWindowPlanner.plan(spans)
        val over = windows.filter { it.length > win }
        assertTrue(over.all { it.firstSpan == it.lastSpan },
            "a merged window must never exceed the cap; got $over")
        assertEquals(2, over.size, "over-cap windows in the fixture")

        // Only >30 s actually costs audio — that is where the recognizer
        // truncates. One window, 0.166 s of 636 s. Pinned so that a VAD-config
        // change which starts dropping seconds of speech fails here rather than
        // showing up as an unexplained WER regression later.
        val truncated = AsrWindowPlanner.overlong(windows)
        assertEquals(1, truncated.size, "windows the recognizer will truncate")
        val lost = truncated.sumOf { it.length - 30 * 16000 } / 16000.0
        assertTrue(lost < 0.25, "audio lost to truncation: ${lost}s")
    }

    @Test
    fun merging_is_greedy_because_every_cut_risks_an_invented_sentence_end() {
        // Pins the rule rather than the corpus: a span that fits is always taken,
        // and the one that would overflow always starts the next window. A
        // "balance the windows" refactor produces more windows and fails here.
        val s = listOf(Span(0, 400), Span(500, 400), Span(1000, 400), Span(1500, 100))
        assertEquals(
            listOf(AsrWindowPlanner.Window(0, 1, 0, 900),
                   AsrWindowPlanner.Window(2, 3, 1000, 1600)),
            AsrWindowPlanner.plan(s, windowSamples = 1000),
        )
        // measured from the window start, not from the previous span's end:
        // span 2 ends at 1400, and 1400 - 0 > 1000, so it cannot join window 0.
    }

    @Test
    fun an_oversized_span_is_emitted_alone_rather_than_looping_forever() {
        val s = listOf(Span(0, 5000), Span(6000, 100))
        val got = AsrWindowPlanner.plan(s, windowSamples = 1000)
        assertEquals(2, got.size)
        assertEquals(5000, got[0].end - got[0].start, "over-length, for the caller to clamp")
    }

    @Test
    fun the_windowed_transcript_lands_within_one_practice_unit_of_macOS() {
        // The end-to-end number R-10 gates on: feed the recognised text through
        // the real segmenter and count practice units. Timings are synthetic and
        // uniform on purpose — only the *text* may drive the split here, which is
        // exactly the property that makes the count comparable to macOS at all.
        val tokens = g.objList("segments").flatMap { it.str("text").trim().split(Regex("\\s+")) }
            .filter { it.isNotEmpty() }
        val words = tokens.mapIndexed { i, w -> TimedWord(w, i * 0.3, i * 0.3 + 0.25) }
        val units = SentenceSegmenter.mergeIntoSentences(words)
        assertEquals(158, units.size, "practice units from the sherpa-onnx text")
        // macOS gold is 159 on the same synthetic-timing basis. Asserted as a
        // band, not equality: R-10's finding is that the two transcripts are ~4%
        // WER apart and always will be (fp32 buys 0.11pp), so pinning an exact
        // match would pin a coincidence. What must not regress is the *distance*.
        assertTrue(kotlin.math.abs(units.size - 159) <= 8,
            "within 5% of the macOS unit count, got ${units.size}")
    }
}
