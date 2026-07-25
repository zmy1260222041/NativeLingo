package com.nativelingo.scoring.io

import java.io.InputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Minimal NumPy `.npy` reader for the golden-fixture format produced by
 * `scripts/capture_golden.py` on macOS (little-endian `f4`/`f8`/`i4`/`i8`/`u1`).
 *
 * Pure JVM, zero dependencies — keeps `:core-scoring` Android-free so the
 * numerical-parity harness runs on plain JVM CI. The macOS backend is the
 * "gold standard source"; this reader ingests what it dumps.
 *
 * See docs/android-migration.md §10 (Layer 1/2 verification strategy).
 */
class NpyArray(
    val shape: IntArray,
    /** Flat row-major payload, promoted to Double for a uniform numeric surface. */
    val data: DoubleArray,
    val dtype: Char,
    val dtypeBytes: Int,
) {
    val size: Int
        get() = if (shape.isEmpty()) 1 else shape.fold(1) { acc, dim -> acc * dim }

    fun rank(): Int = shape.size
}

object NpyReader {
    // \x93NUMPY — the 6-byte magic prefix of every .npy file.
    private val MAGIC = byteArrayOf(0x93.toByte(), 'N'.code.toByte(), 'U'.code.toByte(),
        'M'.code.toByte(), 'P'.code.toByte(), 'Y'.code.toByte())

    fun read(stream: InputStream): NpyArray {
        val bytes = stream.readBytes()
        require(bytes.size >= 10) { "file too small to be .npy (${bytes.size} bytes)" }
        for (i in MAGIC.indices) {
            require(bytes[i] == MAGIC[i]) { "not a .npy file (bad magic at byte $i)" }
        }

        val major = bytes[6].toInt() and 0xFF
        val (headerLen: Int, headerStart: Int) = when (major) {
            1 -> readLeU16(bytes, 8) to 10
            2 -> readLeU32(bytes, 8) to 12
            else -> error("unsupported .npy format version: $major")
        }
        val header = String(bytes, headerStart, headerLen, Charsets.US_ASCII)

        val shape = parseShape(header)
        val (code: Char, dtypeBytes: Int, endian: Char) = parseDtype(header)
        require(endian == '<' || endian == '|' || endian == '=') {
            "only little-endian .npy supported, got '$endian'"
        }

        val n = if (shape.isEmpty()) 1 else shape.fold(1) { acc, dim -> acc * dim }
        val dataStart = headerStart + headerLen
        val payload = ByteBuffer.wrap(bytes, dataStart, n * dtypeBytes)
            .order(ByteOrder.LITTLE_ENDIAN)
        val out = DoubleArray(n)
        when (code) {
            'f' -> when (dtypeBytes) {
                4 -> repeat(n) { out[it] = payload.float.toDouble() }
                8 -> repeat(n) { out[it] = payload.double }
                else -> error("unsupported float dtype f$dtypeBytes")
            }
            'i', 'u' -> when (dtypeBytes) {
                1 -> repeat(n) { out[it] = (payload.get().toInt() and 0xFF).toDouble() }
                2 -> repeat(n) { out[it] = payload.short.toDouble() }
                4 -> repeat(n) { out[it] = payload.int.toLong().toDouble() }
                8 -> repeat(n) { out[it] = payload.long.toDouble() }
                else -> error("unsupported int dtype $code$dtypeBytes")
            }
            else -> error("unsupported dtype category '$code'")
        }
        return NpyArray(shape, out, code, dtypeBytes)
    }

    private fun readLeU16(b: ByteArray, off: Int): Int =
        (b[off].toInt() and 0xFF) or ((b[off + 1].toInt() and 0xFF) shl 8)

    private fun readLeU32(b: ByteArray, off: Int): Int =
        readLeU16(b, off) or
            ((b[off + 2].toInt() and 0xFF) shl 16) or
            ((b[off + 3].toInt() and 0xFF) shl 24)

    private val SHAPE_RE = Regex("""'shape':\s*\(([^)]*)\)""")
    private val DTYPE_RE = Regex("""'descr':\s*'([^']*)'""")

    private fun parseShape(header: String): IntArray {
        val body = SHAPE_RE.find(header)?.groupValues?.get(1)?.trim()
            ?: error("no shape in .npy header")
        if (body.isEmpty()) return IntArray(0) // scalar
        return body.split(',').map { it.trim() }.filter { it.isNotEmpty() }
            .map { it.toInt() }.toIntArray()
    }

    private fun parseDtype(header: String): Triple<Char, Int, Char> {
        val raw = DTYPE_RE.find(header)?.groupValues?.get(1)
            ?: error("no descr in .npy header")
        // e.g. "<f4", "<i8", "|b1", "=u1"
        val endian = if (raw[0] in "<>|=") raw[0] else '|'
        val rest = if (raw[0] in "<>|=") raw.substring(1) else raw
        val code = rest[0]
        val size = rest.substring(1).toInt()
        return Triple(code, size, endian)
    }
}
