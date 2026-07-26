package com.nativelingo.app.gates

import android.os.SystemClock
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nativelingo.asr.SpeechDetector
import com.nativelingo.asr.WhisperTranscriber
import com.nativelingo.models.ModelId
import com.nativelingo.models.WhisperTier
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * R-10 on real hardware: sherpa-onnx whisper `base.en` int8 and Silero VAD.
 *
 * Both of these are JNI over a *statically linked* ONNX Runtime inside the
 * sherpa AAR — a different runtime build from `:core-embed`'s, in the same
 * process. That is the arrangement `:core-asr`'s build file goes out of its way
 * to make safe (static link, no shared `.so` to collide), and until it has run
 * on a device with both loaded, "safe" is a claim about a build file.
 *
 * The transcript bar is exact equality with the desktop int8 output. Not WER —
 * on a 2.5 s sentence WER is either 0 or coarse, and what is being tested here
 * is kernel equivalence, where "close" has no meaning: a beam search either
 * takes the same path or it does not.
 */
@RunWith(AndroidJUnit4::class)
class WhisperDeviceTest {

    private fun transcriber(): WhisperTranscriber {
        val tier = WhisperTier.DEFAULT
        val (enc, dec, tok) = Triple(
            DeviceFixtures.requireModel(tier.encoder),
            DeviceFixtures.requireModel(tier.decoder),
            DeviceFixtures.requireModel(tier.tokens),
        )
        return WhisperTranscriber(enc.absolutePath, dec.absolutePath, tok.absolutePath)
    }

    @Test
    fun transcripts_match_the_desktop_int8_output_verbatim() {
        val golden = DeviceFixtures.assetJson("device/whisper_base_en_int8.json")

        @Suppress("UNCHECKED_CAST")
        val want = golden["text"] as Map<String, String>
        assertEquals("base.en", golden["tier"], "reference was captured on a different tier")

        transcriber().use { asr ->
            // Warmup: the first decode pays session init, and it is also where a
            // JNI/ABI problem would surface as a crash rather than a wrong string.
            asr.decode(DeviceFixtures.float1d("wav/ref_samantha.npy"))

            val diffs = ArrayList<String>()
            for ((name, expected) in want) {
                val samples = DeviceFixtures.float1d("wav/$name.npy")
                val t0 = SystemClock.elapsedRealtime()
                val got = asr.decode(samples)
                val ms = SystemClock.elapsedRealtime() - t0
                Log.i(
                    DeviceFixtures.TAG,
                    "R-10 %-20s %.2fs audio in %d ms (%.1fx realtime): %s".format(
                        name, samples.size / 16000.0, ms, (samples.size / 16000.0) / (ms / 1000.0), got,
                    ),
                )
                if (got.trim() != expected.trim()) diffs.add("$name:\n  device : $got\n  desktop: $expected")
            }
            assertTrue(
                diffs.isEmpty(),
                "arm64 Android transcripts differ from the desktop int8 reference:\n" +
                    diffs.joinToString("\n"),
            )
        }
    }

    @Test
    fun vad_finds_the_single_utterance_in_a_single_sentence_clip() {
        // Not a parity check — there is no VAD golden for these clips, and the
        // 636 s corpus R-10 measured spans on is not something to push to a
        // device. What this establishes is that the Silero JNI path runs on arm64
        // Android at all and that the flush-at-end contract holds: without the
        // flush the final (here: only) segment never closes, and the failure mode
        // is a silently empty span list rather than an error.
        val model = DeviceFixtures.requireModel(ModelId.VAD)
        SpeechDetector(model.absolutePath).use { vad ->
            val samples = DeviceFixtures.float1d("wav/ref_samantha.npy")
            val spans = vad.spans(samples)
            Log.i(
                DeviceFixtures.TAG,
                "R-10 VAD on ${"%.2f".format(samples.size / 16000.0)}s: " +
                    spans.joinToString { "[%.2f,%.2f]".format(it.start / 16000.0, (it.start + it.length) / 16000.0) },
            )
            assertEquals(1, spans.size, "one sentence, one span")
            val covered = spans.sumOf { it.length } / samples.size.toDouble()
            assertTrue(covered > 0.8, "VAD covered only ${"%.0f".format(covered * 100)}% of a clip that is all speech")
        }
    }

    @Test
    fun both_onnx_runtimes_coexist_in_one_process() {
        // :core-asr statically links its own ONNX Runtime; :core-embed uses the
        // onnxruntime-android AAR. Two copies of the same library in one process
        // is exactly the situation that produces a symbol collision or a duplicate
        // global-arena crash, and it is unavoidable here — the analyse path runs
        // transcription and embedding in the same process.
        val ssl = DeviceFixtures.requireModel(ModelId.SSL_ENCODER)
        com.nativelingo.embed.Wav2Vec2Encoder(ssl.absolutePath).use { enc ->
            transcriber().use { asr ->
                val wav = DeviceFixtures.float1d("wav/ref_samantha.npy")
                // Interleaved on purpose: alternating is what the pipeline does,
                // and it is a harsher test of shared global state than running one
                // and then the other.
                val text1 = asr.decode(wav)
                val emb1 = enc.encode(wav)
                val text2 = asr.decode(wav)
                val emb2 = enc.encode(wav)
                assertEquals(text1, text2, "transcription changed after an embedding run")
                assertEquals(1.0, Numeric.cosRaw(emb1, emb2), 1e-6, "embedding changed after a transcription run")
            }
        }
    }
}
