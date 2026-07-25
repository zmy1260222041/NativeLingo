package com.nativelingo.align

import com.nativelingo.scoring.TestJson
import com.nativelingo.scoring.f
import com.nativelingo.scoring.int
import com.nativelingo.scoring.io.NpyReader
import com.nativelingo.scoring.io.frames2d
import com.nativelingo.scoring.objList
import com.nativelingo.scoring.str
import com.nativelingo.scoring.strList
import java.io.File
import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Gate B / R-6, device-side on JVM: MMS forced alignment reproduces the macOS
 * word boundaries.
 *
 * Layered so a failure says *where* it is, and so most of the suite runs without
 * the 338MB model:
 *  1. word spans from the GOLDEN emission — isolates the port (tokenizer,
 *     char→word grouping, frame→seconds convention) from the model. Asserted
 *     EXACTLY: these spans are what FR-8 replay seeks to.
 *  2. the waveform layer_norm port, element-wise against torchaudio.
 *  3. the ONNX int8 run end-to-end — needs build/onnx, skipped if absent.
 */
class ForcedAlignerTest {

    private val goldenDir = "../core-scoring/src/test/resources/golden"
    private val modelPath = "../../build/onnx/mms_fa_int8_transformer.onnx"
    private val sentence = "The quick brown fox jumps over the lazy dog."
    private val words = sentence.trimEnd('.').split(" ")

    private fun npy(path: String) = NpyReader.read(File("$goldenDir/$path").inputStream())
    private fun float1d(path: String): FloatArray {
        val a = npy(path); return FloatArray(a.size) { a.data[it].toFloat() }
    }

    private fun goldenSpansJson() =
        TestJson.obj(File("$goldenDir/mms/ref_samantha_spans.json").readText())

    /** Golden emission — (T, 29) log-probs straight from macOS torchaudio. */
    private fun goldenEmission() = npy("mms/ref_samantha_emission.npy").frames2d()

    @Test
    fun word_spans_from_golden_emission_match_macos_exactly() {
        val em = goldenEmission()
        val g = goldenSpansJson()
        val wav = float1d("wav/ref_samantha.npy")
        assertEquals(g.int("nframes"), em.size, "golden emission frame count")

        val got = alignWords(words, em, wav.size)
        assertNotNull(got, "alignment returned null on the golden emission")
        val goldenWords = g.objList("spans")
        assertEquals(goldenWords.size, got.count { it != null }, "aligned word count")

        for ((i, gw) in goldenWords.withIndex()) {
            val k = got[i]
            assertNotNull(k, "word ${gw.str("word")} unaligned")
            assertEquals(gw.str("word"), words[i], "word order")
            // the golden is stored rounded to 4dp, align_words rounds to 3 —
            // compare on the coarser grid both agree on.
            assertEquals(round3(gw.f("start")), k.startS, "${gw.str("word")}: start")
            assertEquals(round3(gw.f("end")), k.endS, "${gw.str("word")}: end")
        }
    }

    @Test
    fun char_frames_match_torchaudio_per_character() {
        // finer-grained than the word spans: every character's frame range, so a
        // grouping bug can't hide behind a coincidentally-right word boundary.
        val em = goldenEmission()
        val g = goldenSpansJson()
        val goldenChars = g.objList("char_tokens")

        val charIds = ArrayList<Int>()
        for (w in words) for (c in cleanWord(w)) charIds.add(MmsDict.TOKENS.getValue(c))
        assertEquals(goldenChars.size, charIds.size, "flattened character count")

        val logProbs = Array(em.size) { t -> DoubleArray(em[t].size) { em[t][it].toDouble() } }
        val res = com.nativelingo.scoring.viterbi.ctcAlign(logProbs, charIds.toIntArray(), MmsDict.BLANK)
        val byChar = res.spans.filter { it.extPos % 2 == 1 }
            .associate { (it.extPos - 1) / 2 to intArrayOf(it.firstFrame, it.lastFrame + 1) }

        var maxErr = 0
        for ((i, gc) in goldenChars.withIndex()) {
            assertEquals(gc.int("token_id"), charIds[i], "char $i token id")
            val k = byChar[i] ?: error("char $i (${gc.str("char")}) has no span")
            maxErr = maxOf(maxErr, abs(gc.int("start_frame") - k[0]), abs(gc.int("end_frame") - k[1]))
        }
        // Gate B's criterion is ≤1 frame (20ms); on the golden emission the
        // Viterbi is deterministic, so demand exactness and let the 1-frame
        // budget be spent on int8 drift instead.
        assertEquals(0, maxErr, "character frame boundaries differ from torchaudio by $maxErr frame(s)")
    }

    @Test
    fun cleaning_and_tokenization_match_macos() {
        // Verifies the port of `_clean` + the MMS dict against what macOS's
        // tokenizer actually produced, rather than against my reading of the regex.
        val g = TestJson.obj(File("$goldenDir/mms/ref_samantha_tokens.json").readText())
        val goldenCleaned = g.strList("cleaned")
        val goldenWords = g.strList("words")
        assertEquals(goldenWords, words, "word split")
        assertEquals(goldenCleaned, words.map(::cleanWord), "cleaned words")
        assertEquals(intList(g["keep_idx"]), words.indices.filter { cleanWord(words[it]).isNotEmpty() },
            "kept indices")

        val goldenTokens = (g["tokens"] as List<*>).map { intList(it) }
        val mine = words.map { w -> cleanWord(w).map { MmsDict.TOKENS.getValue(it) } }.filter { it.isNotEmpty() }
        assertEquals(goldenTokens, mine, "per-word token ids")
    }

    @Test
    fun cleaning_handles_the_cases_the_reference_sentence_does_not() {
        // the golden sentence is all plain lowercase-able letters, so these
        // branches would otherwise ship unverified.
        assertEquals("wellknown", cleanWord("well-known"), "hyphen stripped, not a separator")
        assertEquals("don't", cleanWord("Don't"), "apostrophe is in the dict, keep it")
        assertEquals("hello", cleanWord("\"Hello,\""), "punctuation stripped")
        assertEquals("", cleanWord("42"), "digits are not in the dict")
        assertEquals("", cleanWord("——"))
        assertEquals("i", cleanWord("I"), "locale-independent lowercase")
    }

    @Test
    fun waveform_layer_norm_matches_torchaudio() {
        val mine = normalizeWaveform(float1d("wav/ref_samantha.npy"))
        val gold = float1d("mms/ref_samantha_wav_normalized.npy")
        assertEquals(gold.size, mine.size, "length")
        var maxDiff = 0.0
        for (i in mine.indices) maxDiff = maxOf(maxDiff, abs(mine[i].toDouble() - gold[i].toDouble()))
        assertTrue(maxDiff < 1e-5, "waveform layer_norm max-diff $maxDiff (need < 1e-5)")
    }

    @Test
    fun star_column_is_appended_as_zeros() {
        // MMS_FA's 29th column. Width matters — the golden emission has it, and a
        // 28-wide emission would still align (star is never a target), so nothing
        // downstream would complain.
        val out = appendStar(arrayOf(floatArrayOf(-1f, -2f), floatArrayOf(-3f, -4f)))
        assertEquals(3, out[0].size)
        assertEquals(0f, out[0][2])
        assertEquals(0f, out[1][2])
        assertEquals(-3f, out[1][0])
        assertEquals(29, goldenEmission()[0].size, "golden emission width")
    }

    @Test
    fun unalignable_words_are_skipped_not_shifted() {
        // a word that cleans to empty must get null and must NOT consume a
        // neighbour's span — that would silently mis-time every later word.
        val em = goldenEmission()
        val wav = float1d("wav/ref_samantha.npy")
        val withNumber = listOf("The", "quick", "42", "brown")
        val got = alignWords(withNumber, em, wav.size)
        assertNotNull(got)
        assertNull(got[2], "'42' cleans to empty and must be unaligned")
        assertNotNull(got[3], "the word after an unalignable one must still align")
        assertTrue(got[3]!!.startS >= got[1]!!.endS - 0.05f, "spans must stay monotonic")

        assertNull(alignWords(listOf("42", "!!"), em, wav.size), "no alignable words → null")
        assertNull(alignWords(words, em, 0), "no samples → null")
    }

    @Test
    fun onnx_int8_alignment_matches_macos_within_one_frame() {
        val model = File(modelPath)
        if (!model.exists()) {
            println("SKIP: model not at $modelPath — run scripts/onnx_export_mms.py")
            return
        }
        val g = goldenSpansJson()
        val spf = g.f("spf")
        val wav = float1d("wav/ref_samantha.npy")

        MmsEmitter(model.absolutePath).use { emitter ->
            val got = ForcedAligner(emitter).align(words, wav)
            assertNotNull(got, "end-to-end alignment returned null")
            val goldenWords = g.objList("spans")
            var maxFrameErr = 0.0f
            for ((i, gw) in goldenWords.withIndex()) {
                val k = assertNotNull(got[i], "${gw.str("word")}: unaligned")
                maxFrameErr = maxOf(
                    maxFrameErr,
                    abs(gw.f("start") - k.startS) / spf,
                    abs(gw.f("end") - k.endS) / spf,
                )
            }
            assertTrue(maxFrameErr <= 1.0f,
                "int8 word boundaries drift $maxFrameErr frames from macOS (Gate B bar: ≤1)")
        }
    }

    private fun round3(x: Float): Float = (Math.rint(x.toDouble() * 1000.0) / 1000.0).toFloat()

    private fun intList(v: Any?): List<Int> = (v as List<*>).map { (it as Number).toInt() }
}
