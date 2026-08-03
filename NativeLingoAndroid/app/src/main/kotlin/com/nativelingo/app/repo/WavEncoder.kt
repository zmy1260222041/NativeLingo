package com.nativelingo.app.repo

import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * 16 kHz mono FloatArray → PCM16 WAV bytes, for uploading a learner take to the
 * cloud Speaking backend (which decodes via soundfile). The inverse of
 * [com.nativelingo.audio.MediaAudioDecoder]: the recorder captures PCM16 at
 * 16 kHz and [com.nativelingo.app.audio.LearnerRecorder.stop] converts to
 * float; here we round-trip back to the wire format.
 */
object WavEncoder {

    fun encodePcm16(samples: FloatArray, sampleRate: Int = 16_000): ByteArray {
        val data = ByteArray(samples.size * 2)
        val buf = ByteBuffer.wrap(data).order(ByteOrder.LITTLE_ENDIAN)
        for (s in samples) {
            val v = (s.coerceIn(-1f, 1f) * 32767f).toInt().coerceIn(-32768, 32767)
            buf.putShort(v.toShort())
        }
        val out = ByteArrayOutputStream(44 + data.size)
        out.write('R'.code); out.write('I'.code); out.write('F'.code); out.write('F'.code)
        writeLe32(out, 36 + data.size)            // chunk size
        out.write('W'.code); out.write('A'.code); out.write('V'.code); out.write('E'.code)
        out.write('f'.code); out.write('m'.code); out.write('t'.code); out.write(' '.code)
        writeLe32(out, 16)                        // fmt chunk size
        writeLe16(out, 1)                         // PCM
        writeLe16(out, 1)                         // mono
        writeLe32(out, sampleRate)
        writeLe32(out, sampleRate * 2)            // byte rate
        writeLe16(out, 2)                         // block align
        writeLe16(out, 16)                        // bits per sample
        out.write('d'.code); out.write('a'.code); out.write('t'.code); out.write('a'.code)
        writeLe32(out, data.size)
        out.write(data)
        return out.toByteArray()
    }

    private fun writeLe16(out: ByteArrayOutputStream, v: Int) {
        out.write(v and 0xFF); out.write((v shr 8) and 0xFF)
    }

    private fun writeLe32(out: ByteArrayOutputStream, v: Int) {
        out.write(v and 0xFF); out.write((v shr 8) and 0xFF)
        out.write((v shr 16) and 0xFF); out.write((v shr 24) and 0xFF)
    }
}
