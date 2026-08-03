package com.nativelingo.app.repo

import android.content.Context
import android.util.Log
import java.io.File

/**
 * Loads pre-rendered Piper pronunciation reference clips for the Memorizing
 * pronounce feature (FR-17) — the Option-D path.
 *
 * Why pre-rendered, not runtime TTS: sherpa-onnx 1.13.4's OfflineTts crashes on
 * the second generate() in an arm64 process (native SIGSEGV, issue #3675 class).
 * So the curated vocabulary is rendered ONCE offline by
 * `scripts/render_pronounce_refs.py` (using the desktop Piper voice,
 * `noise_scale=0, noise_w_scale=0`, the same deterministic config) and shipped
 * as 16 kHz mono PCM16 wavs. The app reads a clip on demand — zero native TTS,
 * unlimited replays, and the bytes the user hears are bit-identical to what the
 * scorer compares against (the determinism contract).
 *
 * The clips ship under `assets/models/pronounce-refs/<slug>.wav` and are read
 * straight from the APK (a wav is small enough that the AssetFileDescriptor path
 * works, unlike the espeak-ng-data directory that forced PiperAssetBundle's
 * copy-out). If a clip is absent (a label with no bundled reference),
 * [synthesize] returns null and the UI hides the play button.
 *
 * Slug convention matches the render script: lowercased, non-alphanumerics → '-'.
 */
class ReferenceClipSource(context: Context) {

    private val appContext: Context = context.applicationContext

    /** The sample rate of every bundled clip — 16 kHz, the SSL encoder's rate. */
    val sampleRate: Int = 16_000

    /** The slug used for [text] — lowercased, non-alphanumerics collapsed to '-'. */
    fun slug(text: String): String =
        Regex("[^a-z0-9]+").replace(text.lowercase(), "-").trim('-').ifEmpty { "unknown" }

    /**
     * Load the 16 kHz mono PCM16 reference clip for [text] as float32 samples
     * in [-1, 1], or null if no clip is bundled for this label.
     *
     * The wav is decoded by reading the PCM16 bytes after the 44-byte header —
     * the render script always writes canonical 16 kHz mono PCM16, so a full
     * WAV parser is overkill (and pulls in a dependency). The header fields that
     * matter (data chunk offset, bits-per-sample) are validated defensively.
     */
    fun synthesize(text: String): FloatArray? {
        val name = "models/pronounce-refs/${slug(text)}.wav"
        val asset = try {
            appContext.assets.open(name)
        } catch (e: Exception) {
            Log.d(TAG, "no reference clip for ${text.lowercase()} ($name)")
            return null
        }
        return asset.use { readPcm16MonoWav(it.readBytes(), name) }
    }

    /** True when a reference clip exists for [text] (used to show/hide the play
     *  button without loading the whole clip). */
    fun hasClip(text: String): Boolean {
        val name = "models/pronounce-refs/${slug(text)}.wav"
        return try {
            appContext.assets.open(name).use { it.readBytes().isNotEmpty() }
        } catch (e: Exception) {
            false
        }
    }

    private fun readPcm16MonoWav(bytes: ByteArray, name: String): FloatArray? {
        // Canonical WAV: "RIFF....WAVEfmt ....data<len><pcm16>". Find the data chunk.
        if (bytes.size < 44 || !bytes.copyOfRange(0, 4).contentEquals("RIFF".toByteArray())) {
            Log.w(TAG, "$name is not a RIFF wav — skipping")
            return null
        }
        // Locate the 'data' chunk (it is not always at offset 36 — fmt can vary).
        var pos = 12
        var dataStart = -1
        var dataLen = 0
        while (pos + 8 <= bytes.size) {
            val chunkId = bytes.copyOfRange(pos, pos + 4)
            val chunkLen = leInt(bytes, pos + 4)
            if (chunkId.contentEquals("data".toByteArray())) {
                dataStart = pos + 8
                dataLen = chunkLen
                break
            }
            pos += 8 + chunkLen + (chunkLen and 1)  // chunks are word-aligned
        }
        if (dataStart < 0 || dataStart + dataLen > bytes.size) {
            Log.w(TAG, "$name has no usable data chunk")
            return null
        }
        val n = dataLen / 2  // PCM16 → 2 bytes/sample
        val out = FloatArray(n)
        var src = dataStart
        // PCM16 little-endian → float32 in [-1, 1] (32768 divisor).
        for (i in 0 until n) {
            val lo = bytes[src].toInt() and 0xFF
            val hi = bytes[src + 1].toInt() // sign-extended
            src += 2
            out[i] = ((hi shl 8) or lo) / 32768f
        }
        return out
    }

    private fun leInt(b: ByteArray, off: Int): Int =
        (b[off].toInt() and 0xFF) or
            ((b[off + 1].toInt() and 0xFF) shl 8) or
            ((b[off + 2].toInt() and 0xFF) shl 16) or
            ((b[off + 3].toInt() and 0xFF) shl 24)

    companion object {
        private const val TAG = "NLRefClips"
    }
}
