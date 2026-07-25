package com.nativelingo.scoring

import com.nativelingo.scoring.io.NpyReader
import com.nativelingo.scoring.io.frames2dDouble
import com.nativelingo.scoring.viterbi.ctcAlign
import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * Gate B · Layer 2 numerical-parity test (R-6): re-run the CTC forced
 * alignment on the macOS-dumped MMS emission and assert each character's frame
 * span matches torchaudio's `get_aligner()` output within ±1 frame (20ms).
 *
 * This is the highest off-by-one risk in the whole port — a wrong skip-blank
 * transition in `CtcViterbi` would shift every word boundary — so it gets a
 * dedicated per-char check against the torchaudio ground truth.
 */
class CtcViterbiParityTest {

    private val frameTol = 1 // manifest.json: tolerances.align_frame

    private fun golden(path: String) =
        javaClass.getResourceAsStream("/golden/$path")
            ?: error("missing golden resource: /golden/$path")

    @Test
    fun mms_forced_align_matches_torchaudio() {
        val emission = NpyReader.read(golden("mms/ref_samantha_emission.npy")).frames2dDouble()
        val json = golden("mms/ref_samantha_spans.json").bufferedReader().use { it.readText() }

        val tokenIds = ints(json, "token_id")
        val startFrames = ints(json, "start_frame")
        val endFrames = ints(json, "end_frame")
        assertTrue(tokenIds.isNotEmpty(), "no char_tokens in golden spans.json")

        val result = ctcAlign(emission, tokenIds.toIntArray(), blank = 0)
        val byExt = result.spans.associateBy { it.extPos }

        var maxErr = 0
        val sb = StringBuilder()
        for (k in tokenIds.indices) {
            val mine = byExt[2 * k + 1]
            assertTrue(mine != null, "CtcViterbi produced no span for char $k (ext ${2 * k + 1})")
            val dStart = abs(mine!!.firstFrame - startFrames[k])
            val dEnd = abs(mine.lastFrame - endFrames[k])
            maxErr = maxOf(maxErr, dStart, dEnd)
            if (dStart > frameTol || dEnd > frameTol) {
                sb.append("char $k: mine[${mine.firstFrame},${mine.lastFrame}] torchaudio[${startFrames[k]},${endFrames[k]}]; ")
            }
        }
        assertTrue(maxErr <= frameTol,
            "CtcViterbi char spans diverge from torchaudio by $maxErr frames (tol $frameTol). $sb")
    }

    private fun ints(json: String, field: String): List<Int> =
        Regex(""""$field":\s*(\d+)""").findAll(json).map { it.groupValues[1].toInt() }.toList()
}
