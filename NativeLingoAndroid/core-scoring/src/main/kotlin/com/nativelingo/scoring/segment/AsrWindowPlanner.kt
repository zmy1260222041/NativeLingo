package com.nativelingo.scoring.segment

/**
 * How a long recording is cut into windows for Whisper (FR-2, FR-M3).
 *
 * sherpa-onnx's offline Whisper takes **at most 30 s per call** — it truncates
 * anything longer and only warns — so long reference audio has to be cut by us.
 * That choice is not a detail: R-10 measured three strategies against the macOS
 * gold transcript and they differ by more than 2x on every metric, because
 * *Whisper punctuates the end of whatever chunk it is handed*. Every cut is a
 * potential invented sentence end, and FR-2/FR-M3 split practice units on
 * `[.!?]`.
 *
 * | strategy                    | WER   | punct. disagreement | units (gold 159) |
 * |-----------------------------|-------|---------------------|------------------|
 * | one call per VAD segment    | 5.56% | 3.17%               | 172              |
 * | fixed 29 s windows          | 5.56% | 1.25%               | 162              |
 * | Whisper's own long-form loop| 3.14% | 1.01%               | 162              |
 * | **VAD segments merged to 29 s** | **4.01%** | **1.65%**   | **158**          |
 *
 * This class implements the last row, and the reason it is not the third
 * (which scores better) is an API limit, not a preference: the long-form loop
 * needs segment-level timestamps to know where to put the cursor, and
 * **sherpa-onnx v1.13.4's Android AAR does not expose them**. Its
 * `OfflineRecognizerResult` has only `text/tokens/timestamps/durations/
 * lang/emotion/event` — no `segmentTimestamps`, even though the Python binding
 * has it and the `enableSegmentTimestamps` config flag exists. The token-
 * timestamp fallback is also dead: the published base.en models are exported
 * without attention outputs, so `timestamps` comes back empty. **On Android we
 * can read `text` and nothing else**, so the strategy had to be one that needs
 * only text.
 *
 * Merging is the best of the text-only options for a reason worth keeping: it
 * makes cuts *rare* (77 VAD segments become 27 windows) and puts every one of
 * them **inside a silence VAD already found**, rather than mid-sentence (per-
 * segment) or mid-word (fixed windows).
 *
 * If sherpa-onnx ever exposes segment timestamps to Kotlin — or once the NDK
 * build for `:core-audio` makes building sherpa-onnx from source cheap — switch
 * to the long-form loop and re-run `scripts/asr_text_parity.py`.
 *
 * Golden fixture: `golden/asr/vadwin_trace.json`.
 */
object AsrWindowPlanner {

    /** Whisper's receptive field is 30 s; 1 s of margin keeps sherpa from truncating. */
    const val WIN_S = 29.0

    /** A speech region found by Silero VAD, in samples. */
    data class Span(val start: Int, val length: Int) {
        val end: Int get() = start + length
    }

    /**
     * One recognizer call: the contiguous audio `[start, end)` covering spans
     * `firstSpan..lastSpan`.
     *
     * The span is *contiguous*, internal silences included — not the speech
     * regions spliced together. Splicing would butt phrases against each other
     * that never met in the real utterance, and Whisper would punctuate the
     * seam.
     */
    data class Window(val firstSpan: Int, val lastSpan: Int, val start: Int, val end: Int) {
        val length: Int get() = end - start
    }

    fun windowSamples(sampleRate: Int = 16_000): Int = (WIN_S * sampleRate).toInt()

    /**
     * Greedily merge [spans] into windows of at most [windowSamples].
     *
     * Greedy is deliberate rather than merely simple: it minimises the number of
     * cuts, and since each cut is what risks an invented sentence end, fewer is
     * better. Balancing the windows evenly would produce *more* of them.
     *
     * **A single span longer than the window is emitted alone and over-length,
     * and this really happens** — 2 of the fixture's 77 spans are (30.17 s and
     * 29.91 s) despite Silero being configured with `max_speech_duration = 25 s`,
     * which sherpa-onnx evidently treats as a hint. Only spans over *30* s cost
     * anything (the recognizer truncates and warns): one, losing 0.166 s of 636 s.
     * The planner reports rather than repairs, because the measured Gate F
     * numbers were produced with the truncation in place — splitting the tail
     * into its own call would add a cut, and an added cut is exactly what R-10
     * showed to be expensive. See [overlong]; `:core-asr` should log it.
     */
    fun plan(spans: List<Span>, windowSamples: Int = windowSamples()): List<Window> {
        val out = ArrayList<Window>()
        var i = 0
        while (i < spans.size) {
            val first = spans[i].start
            var j = i
            while (j + 1 < spans.size && spans[j + 1].end - first <= windowSamples) j++
            out.add(Window(firstSpan = i, lastSpan = j, start = first, end = spans[j].end))
            i = j + 1
        }
        return out
    }

    /**
     * Windows the recognizer will silently truncate, i.e. longer than its real
     * 30 s limit — not [WIN_S], which is our own margin.
     *
     * Separate from [plan] because it is a *reporting* concern: sherpa-onnx
     * prints a C++ warning and drops the tail, which on Android goes nowhere a
     * user or a crash reporter will see it.
     */
    fun overlong(windows: List<Window>, sampleRate: Int = 16_000): List<Window> =
        windows.filter { it.length > 30 * sampleRate }
}
