package com.nativelingo.models

import java.io.File
import java.security.MessageDigest

/** No source had the file. [searched] is what to show a user, in order. */
class MissingModelException(
    val spec: ModelSpec,
    val searched: List<String>,
) : Exception("${spec.fileName}(${spec.requiredBy})未找到。已查找:${searched.joinToString("; ")}")

/**
 * The file is there but is not the artifact the gates were measured on.
 *
 * Separate from [MissingModelException] because the remedies differ: missing
 * means "fetch the asset pack", corrupt means "delete and re-fetch", and a
 * hash mismatch on a *complete* file may also mean a model was re-exported
 * without its gate being re-run (see [ModelCatalog]).
 */
class CorruptModelException(
    val spec: ModelSpec,
    val file: File,
    reason: String,
) : Exception("${spec.fileName} 校验失败($reason)。文件:$file")

/**
 * Resolves [ModelId] to a verified file.
 *
 * @param sources searched in order; the first hit wins. Order encodes trust:
 *   a debug/adb-pushed override directory goes first precisely so a device can
 *   be given a different tier or a re-export without reinstalling.
 * @param stateDir where "this file already passed its checksum" markers live.
 *   Must be app-private storage the user cannot edit — the marker is a cache of
 *   an expensive check, and a marker in the same (pushable) directory as the
 *   model would let a corrupt model carry its own clean bill of health.
 * @param catalog spec lookup. Production always uses [ModelCatalog]; tests
 *   substitute small specs so the failure modes can be exercised without 891 MiB
 *   of weights on hand.
 */
class ModelRegistry(
    private val sources: List<ModelSource>,
    private val stateDir: File,
    private val catalog: (ModelId) -> ModelSpec = ModelCatalog::get,
) {

    /**
     * Path of a model, with the cheap check always applied.
     *
     * Length is compared on every call because it costs a `stat` and catches the
     * overwhelmingly common failure: a download or copy that stopped early. A
     * short file is *not* caught downstream in any useful way — ONNX Runtime
     * throws a protobuf parse error from native code, and sherpa-onnx aborts the
     * process. Full hashing is [verify].
     */
    fun resolve(id: ModelId): File {
        val spec = catalog(id)
        val searched = ArrayList<String>(sources.size)
        for (s in sources) {
            val f = s.locate(spec)
            if (f == null) {
                searched.add(s.description)
                continue
            }
            val len = f.length()
            if (len != spec.bytes) {
                throw CorruptModelException(spec, f, "长度 $len,应为 ${spec.bytes}")
            }
            return f
        }
        throw MissingModelException(spec, searched)
    }

    /** The three files of a whisper tier, in encoder/decoder/tokens order. */
    fun resolveTier(tier: WhisperTier): List<File> = tier.ids.map(::resolve)

    /** True when every file of [tier] is present at the right length. */
    fun hasTier(tier: WhisperTier): Boolean = try {
        resolveTier(tier); true
    } catch (_: MissingModelException) {
        false
    } catch (_: CorruptModelException) {
        false
    }

    /**
     * Full SHA-256 check, memoised per file.
     *
     * Hashing 891 MiB is seconds of I/O, so it belongs in warmup (the macOS
     * `/warmup` analogue), not in the analyse path — but it belongs *somewhere*,
     * because length alone cannot distinguish "asset pack delivered intact" from
     * "flipped a bit on a failing eMMC", and the latter reaches the learner as a
     * plausible-looking wrong score rather than as an error.
     *
     * The marker records the file's length and mtime alongside the digest, so a
     * replaced file re-hashes rather than inheriting the previous verdict.
     */
    fun verify(id: ModelId): File {
        val spec = catalog(id)
        val file = resolve(id)
        val stamp = "${spec.sha256} ${file.length()} ${file.lastModified()}"
        val marker = File(stateDir, "${spec.fileName}.verified")
        if (marker.isFile && runCatching { marker.readText().trim() }.getOrNull() == stamp) {
            return file
        }
        val got = sha256(file)
        if (got != spec.sha256) {
            throw CorruptModelException(spec, file, "SHA-256 $got,应为 ${spec.sha256}")
        }
        stateDir.mkdirs()
        // Written only after the digest passes, so an interrupted verify simply
        // re-verifies next time rather than recording a result it never got.
        runCatching { marker.writeText(stamp) }
        return file
    }

    /**
     * Verify a set of models, reporting progress in bytes so a caller can drive a
     * determinate progress bar. Fails on the first bad file — there is nothing
     * useful to do with the rest.
     */
    fun verifyAll(
        specs: List<ModelSpec> = ModelCatalog.installTime,
        onProgress: (doneBytes: Long, totalBytes: Long) -> Unit = { _, _ -> },
    ) {
        val total = specs.sumOf { it.bytes }
        var done = 0L
        for (spec in specs) {
            verify(spec.id)
            done += spec.bytes
            onProgress(done, total)
        }
    }

    private fun sha256(file: File): String {
        val md = MessageDigest.getInstance("SHA-256")
        // 1 MiB reads: large enough that per-call overhead is noise, small enough
        // to stay out of the large-object path on a low-memory device.
        val buf = ByteArray(1 shl 20)
        file.inputStream().use { ins ->
            while (true) {
                val n = ins.read(buf)
                if (n <= 0) break
                md.update(buf, 0, n)
            }
        }
        return md.digest().joinToString("") { "%02x".format(it) }
    }
}
