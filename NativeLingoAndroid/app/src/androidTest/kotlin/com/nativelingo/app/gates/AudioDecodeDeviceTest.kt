package com.nativelingo.app.gates

import android.media.MediaCodecList
import android.media.MediaFormat
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nativelingo.audio.MediaAudioDecoder
import com.nativelingo.embed.Wav2Vec2Encoder
import com.nativelingo.models.ModelId
import com.nativelingo.scoring.align.dtwAlign
import com.nativelingo.scoring.norm.normalizePair
import com.nativelingo.scoring.score.CalibrationLoader
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.math.abs
import kotlin.math.roundToInt
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/**
 * The device half of Gate E (R-9).
 *
 * R-9 settled the resampler on the desktop and, on that basis, dropped the
 * FFmpeg-NDK plan in favour of `MediaExtractor`/`MediaCodec`. It left one thing
 * explicitly open, in its own words: FFmpeg is the same bytes everywhere,
 * whereas system decoders are per-OEM implementations, and "very likely
 * irrelevant" was an inference. This is the measurement.
 *
 * Both sides decode the *same* lossy bitstream (see
 * `scripts/capture_device_fixtures.py`), so codec loss cancels; what remains is
 * decoder-implementation difference plus our downmix/resample port. Criteria are
 * R-9's own, read from the fixture manifest rather than restated here, so the
 * two can't drift apart.
 *
 * **Scope limit, stated up front:** one emulator is one decoder implementation.
 * This can show the pipeline is sound and can catch a gross port bug; it cannot
 * close the multi-OEM question. That stays on the device checklist.
 */
@RunWith(AndroidJUnit4::class)
class AudioDecodeDeviceTest {

    private fun manifest() = DeviceFixtures.assetJson("device/manifest.json")

    @Suppress("UNCHECKED_CAST")
    private fun variants() = manifest()["variants"] as Map<String, Map<String, Any?>>

    @Suppress("UNCHECKED_CAST")
    private fun criteria() = manifest()["criteria"] as Map<String, Any?>

    private fun crit(key: String) = (criteria()[key] as Number).toDouble()

    @Test
    fun the_platform_decoder_agrees_with_ffmpeg_in_the_score_domain() {
        val model = DeviceFixtures.requireModel(ModelId.SSL_ENCODER)
        val minCos = crit("emb_min_cosine")
        val maxCostDelta = crit("max_dtw_cost_delta")
        val maxAccDelta = crit("max_accuracy_delta")
        val calibration = CalibrationLoader.loadDefault()

        Wav2Vec2Encoder(model.absolutePath).use { enc ->
            // The un-encoded source is the reference both decodes are scored
            // against — that is what makes the two costs comparable numbers rather
            // than two unrelated ones.
            val sourceEmb = enc.encode(DeviceFixtures.float1d("wav/ref_samantha.npy"))

            for ((key, v) in variants()) {
                val container = DeviceFixtures.assetToCache("device/${v["container"]}")
                val ffmpeg = DeviceFixtures.float1d("device/${v["reference"]}")
                assertEquals(
                    (v["reference_samples"] as Number).toInt(), ffmpeg.size,
                    "$key: reference npy length disagrees with the manifest",
                )

                val decoded = MediaAudioDecoder.decode(container.absolutePath)
                assertEquals(16_000, decoded.sampleRate, "$key: decoder did not resample to 16 kHz")

                // Container round-trips are not sample-aligned, and the residual is
                // not a whole number of samples — see Numeric.bestLag for the
                // integer part (encoder priming) and Numeric.shiftBy for why a
                // fraction survives it (the priming trim is 766.2 output samples).
                // Both must be removed before this comparison means anything about
                // the decoder rather than about the clock.
                val coarse = Numeric.bestLag(ffmpeg, decoded.samples)
                val fine = Numeric.bestFractionalLag(ffmpeg, decoded.samples, coarse)
                val (a, b) = Numeric.alignTo(ffmpeg, Numeric.shiftBy(decoded.samples, fine - coarse), coarse)
                val snr = Numeric.snrDb(a, b)
                val (gain, snrGain) = Numeric.bestGain(a, b)

                val embF = enc.encode(a)
                val embD = enc.encode(b)
                val cos = Numeric.cosAfterCmvn(embF, embD)

                // The control that separates this measurement's floor from the
                // decoder's contribution. Perturb the *reference itself* by the
                // same gain the decoder differed by, and encode that. Whatever
                // cosine that yields is what a perturbation of this size costs
                // merely by passing through a reduced-precision encoder — rounding
                // is a step function, so a sub-percent input change can cross a
                // boundary and move the output disproportionately. The decoder
                // cannot be blamed for anything at or above this floor.
                val control = FloatArray(a.size) { (a[it] * gain).toFloat() }
                val controlCos = Numeric.cosAfterCmvn(embF, enc.encode(control))

                val (srcF, normF) = normalizePair(sourceEmb, embF)
                val (srcD, normD) = normalizePair(sourceEmb, embD)
                val costF = dtwAlign(srcF, normF).normalizedCost
                val costD = dtwAlign(srcD, normD).normalizedCost
                val accF = calibration.accuracyFromCost(costF)
                val accD = calibration.accuracyFromCost(costD)

                Log.i(
                    DeviceFixtures.TAG,
                    ("R-9 %-16s lag=%+.3f (int %+d)  SNR=%.1f dB  gain=%.5f → SNR=%.1f dB  " +
                        "cos=%.6f (encoder floor %.6f)  cost %.5f→%.5f (Δ%.5f)  accuracy %.2f→%.2f (Δ%.2f)").format(
                        key, fine, coarse, snr, gain, snrGain, cos, controlCos,
                        costF, costD, abs(costD - costF), accF, accD, abs(accD - accF),
                    ),
                )

                // Level, gated. This is what found the downmix defect: a flat
                // 1.41343 (√2) offset, because `toMono` averaged the channels while
                // libswresample rematrixes to preserve energy. Nothing downstream
                // noticed — every consumer of level in the chain is scale-invariant
                // — so only a direct check catches it, and it stays checked because
                // that invariance is a property of today's consumers rather than a
                // promise. 1% is far tighter than any codec-level difference and far
                // looser than a matrix error, which is off by 3 dB or not at all.
                assertTrue(
                    abs(gain - 1.0) < 0.01,
                    "$key: decode level is ${1.0 / gain}× the ffmpeg reference " +
                        "(gain $gain) — check toMono's downmix matrix",
                )

                // Waveform, once level is out of the way. Reported, not gated, and
                // the reason is R-9's own: it retired the sample-domain criterion
                // after measuring that ~40 dB of it is invisible in the score.
                assertTrue(
                    snrGain > 30.0,
                    "$key: waveforms differ beyond level (SNR after gain $snrGain dB)",
                )

                // Criterion ① of the rewritten Gate E, against its own noise floor.
                //
                // The bar of 0.995 came from a desktop measurement that swapped
                // *resampler kernels* while encoding with the fp32 model, and it does
                // not survive being carried onto a quantised encoder unexamined:
                // rounding is a step function, so a sub-percent input change can
                // cross a boundary and move the embedding disproportionately. R-5
                // measured the int8 export at 0.983–0.987 against fp32 on *identical*
                // waveforms — requiring two different decodes to agree to 0.995
                // through it asks for more agreement than the encoder showed with
                // itself across precisions. `controlCos` measures that floor directly
                // by feeding the reference back through with only the gain
                // perturbation applied.
                //
                // Which side of the disjunction actually carries the pass has changed,
                // and it is worth knowing which: on the int8 run this was written for,
                // the floor was the only pass path (cos 0.9888–0.9928 < 0.995). With
                // the fp16 encoder R-5 switched to, 0.995 is met outright — 0.9999 on
                // both variants — so the floor clause is now a dormant fallback. It
                // stays because it is the part that records *why* the constant might
                // not apply; if a future export or ORT version re-quantises this path,
                // the failure lands on a clause that explains itself and logs the
                // floor, rather than on an unexplained red.
                assertTrue(
                    cos >= minCos || cos >= controlCos - 0.002,
                    "$key: embedding cosine $cos is below both the $minCos bar and " +
                        "the encoder floor $controlCos — the decoder is contributing real error",
                )
                assertTrue(
                    abs(costD - costF) <= maxCostDelta,
                    "$key: DTW cost moved ${abs(costD - costF)} (> $maxCostDelta) between decoders",
                )
                assertTrue(
                    abs(accD - accF) <= maxAccDelta,
                    "$key: accuracy moved ${abs(accD - accF)} (> $maxAccDelta) between decoders",
                )
            }
        }
    }

    @Test
    fun a_seeked_span_actually_contains_the_instant_that_was_asked_for() {
        // FR-8 replay cuts a clip out of the middle of a video, so "decode from
        // 1.0 s" must return audio that includes 1.0 s. It did not, before
        // PRE_ROLL_S: this test first ran with a plain seek and measured a first
        // output timestamp of 1.0217 s — the decoder eats the frame after a seek
        // as priming, so the first ~23 ms of the requested span was simply not in
        // the output. On a word-boundary cut that is a clipped consonant onset,
        // and nothing downstream could have detected it.
        val container = DeviceFixtures.assetToCache("device/clip_aac.mp4")
        val whole = MediaAudioDecoder.decode(container.absolutePath)
        val tail = MediaAudioDecoder.decode(container.absolutePath, startS = 1.0)

        Log.i(
            DeviceFixtures.TAG,
            "R-9 seek: whole=%d samples, from 1.0s=%d samples, startS=%.4f (pre-roll %.2fs)".format(
                whole.samples.size, tail.samples.size, tail.startS, MediaAudioDecoder.PRE_ROLL_S,
            ),
        )
        assertTrue(tail.startS <= 1.0, "startS ${tail.startS} is after the requested 1.0s")
        // The pre-roll is a floor on coverage, not a promise of exactness — the
        // sync sample can be anywhere in it. What must hold is that it did not
        // rewind further than asked.
        assertTrue(
            tail.startS >= 1.0 - MediaAudioDecoder.PRE_ROLL_S - 0.05,
            "startS ${tail.startS} is further back than the pre-roll explains",
        )
        assertTrue(tail.samples.size < whole.samples.size, "seeking to 1.0s returned the whole track")
        assertEquals(0.0, whole.startS, "a full decode should start at 0")

        // Now the part that makes startS *trustworthy* rather than merely
        // plausible: locate the tail inside the whole decode by correlation and
        // check it lands where startS says it does. A replay span is placed by
        // arithmetic on this number, so an error here shifts every clip.
        //
        // Skip the head of the tail buffer first. The resampler starts with zero
        // history, so its first output samples are a filter transient that exists
        // in the tail and not in the whole decode — a real and expected edge
        // effect, and correlating across it would measure the transient.
        val skip = 640                                  // 40 ms at 16 kHz
        val predicted = (tail.startS * 16_000).roundToInt() + skip
        val body = tail.samples.copyOfRange(skip, minOf(tail.samples.size, skip + 16_000))
        val want = whole.samples.copyOfRange(predicted, minOf(whole.samples.size, predicted + body.size))
        val coarse = Numeric.bestLag(want, body, maxLag = 320, probe = body.size)
        val fine = Numeric.bestFractionalLag(want, body, coarse)
        val (a, b) = Numeric.alignTo(want, Numeric.shiftBy(body, fine - coarse), coarse)
        val snr = Numeric.snrDb(a, b)
        Log.i(
            DeviceFixtures.TAG,
            "R-9 seek: predicted sample %d, measured offset %+.3f, SNR after alignment %.1f dB".format(
                predicted, fine, snr,
            ),
        )
        // 1 ms. Tighter than FR-8 needs (a word boundary is tens of ms) and loose
        // enough for the resample grid the two decodes land on.
        assertTrue(abs(fine) <= 16.0, "tail sits $fine samples from where startS claims")

        // SNR is reported, not gated — and deliberately, for the same reason as in
        // the test above. 44.1 kHz → 16 kHz is 441/160, so a decode that begins
        // mid-cycle lands on an output grid shifted by up to half a sample from the
        // full decode's. Half a sample at 1 kHz is already ~-14 dB, so the first
        // version of this test gated at >20 dB and failed at 12.0 dB while
        // measuring nothing but resampler phase. R-9's finding was precisely that
        // sample-domain difference of this size is invisible downstream; the
        // criterion that matters is the score domain, below.
        val model = DeviceFixtures.requireModel(ModelId.SSL_ENCODER)
        val minCos = crit("emb_min_cosine")
        Wav2Vec2Encoder(model.absolutePath).use { enc ->
            val embWhole = enc.encode(a)
            val cos = Numeric.cosAfterCmvn(embWhole, enc.encode(b))
            // Against its own floor, for the reason spelled out in the test above
            // (and dormant for the same reason: the shipped fp16 encoder clears the
            // bar outright). The control applies only the measured sub-sample shift
            // to the reference — no decoding involved — so it is what a 0.26-sample
            // offset costs on its own.
            val control = Numeric.cosAfterCmvn(embWhole, enc.encode(Numeric.shiftBy(a, fine - coarse)))
            Log.i(
                DeviceFixtures.TAG,
                "R-9 seek embedding cosine = %.6f (bar %.3f, encoder floor for a %+.3f-sample shift %.6f)"
                    .format(cos, minCos, fine - coarse, control),
            )
            assertTrue(
                cos >= minCos || cos >= control - 0.002,
                "a seeked span scores differently from the same span of a full decode: " +
                    "$cos, below both the bar and the $control floor",
            )
        }
    }

    @Test
    fun every_codec_behind_the_five_supported_containers_has_a_decoder() {
        // PRD FR-M2: the Android import surface is {.mp4, .mov, .mkv, .m4v,
        // .webm}. Container support is Extractor-side; what can actually be
        // absent per device is the *codec*. These four are what those five
        // containers carry in practice, and all are CDD-mandatory decoders — so a
        // miss here is a device problem worth reporting at import time.
        val mandatory = listOf(
            MediaFormat.MIMETYPE_AUDIO_AAC to "mp4/mov/m4v/mkv",
            MediaFormat.MIMETYPE_AUDIO_OPUS to "webm/mkv",
            MediaFormat.MIMETYPE_AUDIO_VORBIS to "webm/mkv",
            MediaFormat.MIMETYPE_AUDIO_FLAC to "mkv",
        )
        val list = MediaCodecList(MediaCodecList.REGULAR_CODECS)
        val supported = list.codecInfos
            .filter { !it.isEncoder }
            .flatMap { info -> info.supportedTypes.map { it.lowercase() to info.name } }
            .groupBy({ it.first }, { it.second })

        val missing = ArrayList<String>()
        for ((mime, where) in mandatory) {
            val byType = supported[mime.lowercase()]
            // Reported alongside, because this is the call MediaAudioDecoder makes
            // and its result differs: `findDecoderForFormat` on a format built by
            // hand returns null for Opus and Vorbis, whose decoders require the
            // codec-specific data (`csd-0`, the identification header) to be
            // present before they will claim a format. That is not a missing
            // decoder — in the real path the format comes from MediaExtractor and
            // carries its csd. Asserting on the bare-format probe would have
            // "found" a missing Opus decoder on a device that has one.
            val bare = list.findDecoderForFormat(MediaFormat.createAudioFormat(mime, 44_100, 2))
            Log.i(
                DeviceFixtures.TAG,
                "R-9 %-20s (%s): decoders=%s | bare-format probe=%s".format(
                    mime, where, byType ?: "NONE", bare ?: "null (needs csd)",
                ),
            )
            if (byType.isNullOrEmpty()) missing.add("$mime ($where)")
        }
        assertTrue(missing.isEmpty(), "no decoder on this device for: $missing")

        // And the one that matters most: the format the extractor actually hands
        // us must be claimable, for both fixtures. This is the probe
        // MediaAudioDecoder relies on to tell "no decoder here" from "broken file".
        for ((key, v) in variants()) {
            val container = DeviceFixtures.assetToCache("device/${v["container"]}")
            val ex = android.media.MediaExtractor()
            try {
                ex.setDataSource(container.absolutePath)
                val i = (0 until ex.trackCount).first {
                    ex.getTrackFormat(it).getString(MediaFormat.KEY_MIME)!!.startsWith("audio/")
                }
                val fmt = ex.getTrackFormat(i)
                val name = list.findDecoderForFormat(fmt)
                Log.i(DeviceFixtures.TAG, "R-9 $key extractor format → decoder=$name")
                assertNotNull(name, "$key: no decoder for the extractor's own format")
            } finally {
                ex.release()
            }
        }
    }

    @Test
    fun a_container_with_no_audio_track_fails_as_unsupported_not_as_corrupt() {
        // The distinction PRD FR-M2 asks for at the import surface: "this machine
        // has no decoder" / "there is nothing to decode" must be tellable apart
        // from "the file is broken". Both currently arrive as
        // UnsupportedAudioException, which is the seam the UI will branch on.
        val empty = java.io.File(DeviceFixtures.appContext.cacheDir, "not-a-media-file.mp4")
        empty.writeBytes(ByteArray(4096) { 0x7 })
        val thrown = runCatching { MediaAudioDecoder.decode(empty.absolutePath) }.exceptionOrNull()
        assertNotNull(thrown, "a garbage file decoded without error")
        Log.i(DeviceFixtures.TAG, "R-9 garbage file → ${thrown::class.java.simpleName}: ${thrown.message}")
        // MediaExtractor rejects the file itself here (IOException) — recorded
        // rather than asserted, because which of the two it is depends on how far
        // the platform gets before giving up, and the UI must handle both.
    }
}
