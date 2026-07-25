package com.nativelingo.scoring

import com.nativelingo.scoring.io.NpyReader
import com.nativelingo.scoring.io.WavIo
import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.fail

/**
 * FR-8 replay clips: the Kotlin WAV writer must produce what `soundfile` does.
 *
 * Asserted byte-for-byte over the whole file rather than "close enough audio",
 * because every plausible-but-wrong float->int16 conversion is off by at most
 * one LSB (see WavIo's docs). That is inaudible, so a listening test would pass
 * while the Android clip quietly stopped being the macOS clip.
 */
class WavIoParityTest {

    private fun golden(name: String) =
        javaClass.getResourceAsStream("/golden/audio/$name")
            ?: error("missing golden resource: /golden/audio/$name")

    private fun float1d(name: String): FloatArray {
        val a = NpyReader.read(golden(name))
        return FloatArray(a.size) { a.data[it].toFloat() }
    }

    @Test
    fun pcm16_output_is_byte_identical_to_soundfile() {
        val clip = float1d("clip_in.npy")
        val expected = golden("clip_pcm16.wav").readBytes()
        val mine = WavIo.writePcm16(clip, 16000)

        assertEquals(expected.size, mine.size, "file size (44-byte header + 2 bytes/sample)")
        if (!expected.contentEquals(mine)) {
            val at = expected.indices.first { expected[it] != mine[it] }
            val where = if (at < 44) "header byte $at" else "sample ${(at - 44) / 2}"
            fail("differs at $where: expected ${expected[at]}, got ${mine[at]}")
        }
    }

    @Test
    fun the_conversion_is_floor_not_round() {
        // Pins the finding itself, so a future "cleanup" to the obvious idiom
        // fails here with a clear reason instead of only in the byte compare.
        assertEquals(0.toShort(), WavIo.toPcm16(0f))
        assertEquals(16384.toShort(), WavIo.toPcm16(0.5f))
        assertEquals((-16384).toShort(), WavIo.toPcm16(-0.5f))
        // 0.500015 * 32768 = 16384.49 -> floor 16384 (round-to-nearest agrees here)
        assertEquals(16384.toShort(), WavIo.toPcm16(0.500015f))
        // 0.50002 * 32768 = 16384.66 -> floor 16384, but rint would give 16385
        assertEquals(16384.toShort(), WavIo.toPcm16(0.50002f))
        // negatives round away from zero, which trunc would not do
        assertEquals((-16385).toShort(), WavIo.toPcm16(-0.50002f))
        // clamping: +1.0 would scale to 32768, one past the int16 ceiling
        assertEquals(32767.toShort(), WavIo.toPcm16(1.0f))
        assertEquals(32767.toShort(), WavIo.toPcm16(2.5f))
        assertEquals((-32768).toShort(), WavIo.toPcm16(-1.0f))
        assertEquals((-32768).toShort(), WavIo.toPcm16(-2.5f))
    }

    @Test
    fun reading_back_matches_what_soundfile_reads() {
        val expected = float1d("clip_roundtrip.npy")
        val got = WavIo.readPcm16(golden("clip_pcm16.wav"))
        assertEquals(16000, got.sampleRate, "sample rate from the header")
        assertEquals(1, got.channels, "channel count")
        assertEquals(expected.size, got.wav.size, "sample count")
        for (i in expected.indices) {
            assertEquals(expected[i], got.wav[i], "sample $i")   // exact: both are s/32768
        }
    }

    @Test
    fun write_then_read_is_lossless_within_one_lsb() {
        val clip = float1d("clip_in.npy")
        val back = WavIo.readPcm16(WavIo.writePcm16(clip, 16000).inputStream()).wav
        var maxErr = 0.0
        for (i in clip.indices) maxErr = maxOf(maxErr, abs(clip[i].toDouble() - back[i].toDouble()))
        // one LSB at scale 32768; floor (not nearest) means the bound is 1 LSB, not half
        assertTrue(maxErr <= 1.0 / 32768.0 + 1e-9, "round-trip error $maxErr exceeds one LSB")
    }

    @Test
    fun extra_chunks_before_data_are_skipped() {
        // Files arriving from a share-sheet import routinely carry LIST/fact
        // chunks; a writer-shaped reader that assumes data at offset 36 would
        // read chunk text as audio.
        val src = WavIo.writePcm16(FloatArray(64) { (it - 32) / 64f }, 16000)
        val listChunk = "LIST".toByteArray() + byteArrayOf(4, 0, 0, 0) + "INFO".toByteArray()
        val patched = src.copyOfRange(0, 36) + listChunk + src.copyOfRange(36, src.size)
        // fix the RIFF size so the file stays well-formed
        val riffSize = patched.size - 8
        for (k in 0 until 4) patched[4 + k] = ((riffSize shr (8 * k)) and 0xFF).toByte()

        val a = WavIo.readPcm16(src.inputStream()).wav
        val b = WavIo.readPcm16(patched.inputStream()).wav
        assertEquals(a.size, b.size, "the LIST chunk must not be read as audio")
        assertTrue(a.contentEquals(b))
    }

    @Test
    fun a_truncated_data_chunk_still_reads() {
        // An app killed mid-write leaves a full-length declared size with short
        // payload. Losing the take entirely is worse than returning what's there.
        val src = WavIo.writePcm16(FloatArray(1000) { 0.25f }, 16000)
        val cut = src.copyOfRange(0, src.size - 500)   // header still claims 1000 samples
        val got = WavIo.readPcm16(cut.inputStream()).wav
        assertEquals(750, got.size, "should return the samples actually present")
        assertTrue(got.all { abs(it - 0.25f) < 1e-4f })
    }
}
