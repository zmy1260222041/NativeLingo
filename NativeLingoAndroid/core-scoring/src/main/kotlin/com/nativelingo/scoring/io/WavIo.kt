package com.nativelingo.scoring.io

import java.io.InputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * 16-bit PCM WAV reader/writer — the FR-8 replay path.
 *
 * macOS slices replay clips with `soundfile` (`main.py`: `sf.write(..., subtype="PCM_16")`).
 * Android has no libsndfile, so this is a hand-rolled canonical 44-byte
 * RIFF/WAVE writer, verified **byte-identical** against soundfile's output on a
 * golden clip (`golden/audio/clip_pcm16.wav`).
 *
 * ### The float -> int16 conversion is `floor(x * 32768)`
 *
 * Not the idiom you would write from memory. Measured against soundfile's bytes
 * over all 16000 samples of the golden clip:
 *
 * | conversion                      | mismatches |
 * |---------------------------------|------------|
 * | `floor(x * 32768)`              | **0**      |
 * | `rint(x * 32768)`               | 7983       |
 * | `trunc(x * 32768)`              | 9165 (all negative samples) |
 * | `rint(x * 32767)`               | 8184       |
 *
 * So it rounds toward negative infinity, and the scale is 32768 (confirmed by
 * read-back being exactly `s / 32768`). Every wrong variant is off by at most
 * one LSB — inaudible, and precisely why this would never surface as a bug
 * report; it would just quietly mean the Android clip is not the macOS clip.
 * The mechanism inside libsndfile is not established here; the fixture is the
 * contract, and the test compares the whole file, header included.
 */
object WavIo {

    private const val HEADER_BYTES = 44
    private const val SCALE = 32768.0

    /** Canonical 44-byte mono/16-bit WAV. */
    fun writePcm16(wav: FloatArray, sampleRate: Int = 16000, channels: Int = 1): ByteArray {
        require(channels >= 1) { "channels must be >= 1" }
        val dataBytes = wav.size * 2
        val buf = ByteBuffer.allocate(HEADER_BYTES + dataBytes).order(ByteOrder.LITTLE_ENDIAN)
        val blockAlign = channels * 2

        buf.put("RIFF".toByteArray(Charsets.US_ASCII))
        buf.putInt(36 + dataBytes)          // RIFF chunk size = total - 8
        buf.put("WAVE".toByteArray(Charsets.US_ASCII))
        buf.put("fmt ".toByteArray(Charsets.US_ASCII))
        buf.putInt(16)                      // PCM fmt chunk size
        buf.putShort(1)                     // audioFormat = PCM
        buf.putShort(channels.toShort())
        buf.putInt(sampleRate)
        buf.putInt(sampleRate * blockAlign) // byteRate
        buf.putShort(blockAlign.toShort())
        buf.putShort(16)                    // bitsPerSample
        buf.put("data".toByteArray(Charsets.US_ASCII))
        buf.putInt(dataBytes)
        for (v in wav) buf.putShort(toPcm16(v))
        return buf.array()
    }

    /** See the class docs: floor, scale 32768, clamped to the int16 range. */
    fun toPcm16(sample: Float): Short {
        val scaled = Math.floor(sample.toDouble() * SCALE)
        val clamped = if (scaled < -32768.0) -32768.0 else if (scaled > 32767.0) 32767.0 else scaled
        return clamped.toInt().toShort()
    }

    /**
     * Read a 16-bit PCM WAV back to float32 in `[-1, 1)`, dividing by 32768 —
     * which is what `soundfile.read(dtype="float32")` returns, exactly.
     *
     * Chunks are walked rather than assumed at fixed offsets: we write canonical
     * 44-byte headers, but files arriving from elsewhere (a share-sheet import)
     * routinely carry `LIST`/`fact` chunks before `data`.
     */
    fun readPcm16(stream: InputStream): WavData {
        val b = stream.readBytes()
        require(b.size >= 12) { "too small to be a WAV (${b.size} bytes)" }
        require(ascii(b, 0, 4) == "RIFF" && ascii(b, 8, 4) == "WAVE") { "not a RIFF/WAVE file" }

        var pos = 12
        var sampleRate = -1
        var channels = -1
        var bits = -1
        var dataOff = -1
        var dataLen = -1
        while (pos + 8 <= b.size) {
            val id = ascii(b, pos, 4)
            val size = le32(b, pos + 4)
            val body = pos + 8
            require(size >= 0) { "chunk '$id' declares a size that overflows Int" }
            when (id) {
                "fmt " -> {
                    require(body + 16 <= b.size) { "truncated fmt chunk" }
                    channels = le16(b, body + 2)
                    sampleRate = le32(b, body + 4)
                    bits = le16(b, body + 14)
                }
                "data" -> {
                    dataOff = body
                    // Trust the file's length over the declared size: a
                    // truncated recording (app killed mid-write) still has a
                    // full-length header, and refusing to read it would lose
                    // the take entirely.
                    dataLen = minOf(size, b.size - body)
                }
            }
            if (dataOff >= 0 && sampleRate > 0) break
            pos = body + size + (size and 1)   // chunks are word-aligned
        }
        require(dataOff >= 0 && dataLen >= 0) { "no data chunk" }
        require(bits == 16) { "only 16-bit PCM supported, got $bits-bit" }
        require(channels >= 1) { "bad channel count: $channels" }

        val frames = dataLen / (2 * channels)
        val out = FloatArray(frames)
        val payload = ByteBuffer.wrap(b, dataOff, frames * 2 * channels).order(ByteOrder.LITTLE_ENDIAN)
        if (channels == 1) {
            for (i in 0 until frames) out[i] = (payload.short / SCALE).toFloat()
        } else {
            // Mix down to mono the same way audio_io.load_audio does (mean).
            for (i in 0 until frames) {
                var acc = 0.0
                repeat(channels) { acc += payload.short / SCALE }
                out[i] = (acc / channels).toFloat()
            }
        }
        return WavData(out, sampleRate, channels)
    }

    private fun ascii(b: ByteArray, off: Int, len: Int) = String(b, off, len, Charsets.US_ASCII)

    private fun le16(b: ByteArray, off: Int): Int =
        (b[off].toInt() and 0xFF) or ((b[off + 1].toInt() and 0xFF) shl 8)

    private fun le32(b: ByteArray, off: Int): Int =
        le16(b, off) or ((b[off + 2].toInt() and 0xFF) shl 16) or ((b[off + 3].toInt() and 0xFF) shl 24)
}

/** Decoded mono float32 audio plus the header's sample rate and original channel count. */
class WavData(val wav: FloatArray, val sampleRate: Int, val channels: Int)
