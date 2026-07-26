package com.nativelingo.models

import java.io.File
import java.security.MessageDigest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * JVM tests for the catalog's internal consistency and the registry's failure
 * modes. No real models — those are 935 MiB and belong to the device harness.
 * What is tested here is everything that can be wrong *about* them.
 */
class ModelRegistryTest {

    // --- catalog ---------------------------------------------------------------

    @Test
    fun every_id_has_a_spec() {
        // ModelCatalog.get() errors on a gap; `all` walks every enum entry.
        assertEquals(ModelId.entries.size, ModelCatalog.all.size)
    }

    @Test
    fun hashes_are_well_formed_and_distinct_per_distinct_file() {
        val hex = Regex("^[0-9a-f]{64}$")
        for (spec in ModelCatalog.all) {
            assertTrue(hex.matches(spec.sha256), "${spec.id} sha256 is not 64 lowercase hex")
            assertTrue(spec.bytes > 0, "${spec.id} has non-positive length")
            assertTrue(spec.requiredBy.isNotBlank(), "${spec.id} has no requiredBy text")
        }
        // Same file name must imply same bytes+hash, and vice versa. The two
        // whisper tiers legitimately share a tokens file, so this is grouped by
        // name rather than asserted globally distinct.
        for ((name, group) in ModelCatalog.all.groupBy { it.fileName }) {
            assertEquals(1, group.map { it.sha256 to it.bytes }.distinct().size,
                "$name appears with conflicting length/hash")
        }
        // A hash shared across two *names* is allowed only where the files really
        // are byte-identical on purpose. Today there is exactly one such pair: the
        // two whisper tiers ship the same 51864-token vocabulary under per-tier
        // names, as k2-fsa packages it. Anything else sharing a hash is a
        // copy-paste error in the catalog — the kind that would silently point one
        // model at another model's weights.
        val knownIdenticalContent = setOf(setOf("base.en-tokens.txt", "tiny.en-tokens.txt"))
        for ((h, group) in ModelCatalog.all.groupBy { it.sha256 }) {
            val names = group.map { it.fileName }.toSet()
            if (names.size == 1) continue
            assertTrue(names in knownIdenticalContent,
                "hash $h is shared by $names — if that is intended, allowlist it here")
        }
    }

    @Test
    fun install_time_set_is_everything_but_the_tiny_tier() {
        val installIds = ModelCatalog.installTime.map { it.id }.toSet()
        for (id in WhisperTier.TINY_EN.ids) {
            assertFalse(id in installIds, "$id must not be in the install-time pack (R-11)")
        }
        for (id in WhisperTier.BASE_EN.ids) {
            assertTrue(id in installIds, "$id is the release tier and must ship (NFR-4②)")
        }
        // FR-11's model is lazily *loaded*, not lazily fetched — see ModelCatalog.
        assertTrue(ModelId.ESPEAK_MDD in installIds)
    }

    @Test
    fun byte_totals_are_the_numbers_the_prd_quotes() {
        // Pinned so a catalog edit that moves the install footprint is visible in
        // a diff, not discovered when Play rejects the bundle.
        assertEquals(1_084_192_213L, ModelCatalog.TOTAL_BYTES)
        assertEquals(980_565_022L, ModelCatalog.INSTALL_TIME_BYTES)
        // Asset-pack ceiling for an install-time pack is 1.5 GB.
        assertTrue(ModelCatalog.INSTALL_TIME_BYTES < 1_500_000_000L)
    }

    @Test
    fun base_tier_is_the_default() {
        assertEquals(WhisperTier.BASE_EN, WhisperTier.DEFAULT)
    }

    // --- registry --------------------------------------------------------------

    private fun tmp(name: String): File =
        File.createTempFile("nl-$name", "").let { it.delete(); it.mkdirs(); it }

    /** A stand-in spec so the tests do not need 100 MiB of real weights. */
    private fun fakeCatalogFile(dir: File, spec: ModelSpec, bytes: ByteArray) =
        File(dir, spec.fileName).apply { writeBytes(bytes) }

    private fun sha256(b: ByteArray) = MessageDigest.getInstance("SHA-256")
        .digest(b).joinToString("") { "%02x".format(it) }

    @Test
    fun missing_model_names_every_source_it_looked_in() {
        val a = tmp("a"); val b = tmp("b")
        val reg = ModelRegistry(
            listOf(DirectoryModelSource(a, "调试推送目录"), DirectoryModelSource(b, "安装时资源包")),
            tmp("state"),
        )
        val e = assertFailsWith<MissingModelException> { reg.resolve(ModelId.VAD) }
        assertEquals(listOf("调试推送目录", "安装时资源包"), e.searched)
        // The message is user-facing: it must say what the learner loses.
        assertTrue(e.message!!.contains("转写切窗与录音检测"), e.message!!)
    }

    @Test
    fun a_truncated_file_fails_on_length_before_any_hashing() {
        val dir = tmp("trunc")
        val spec = ModelCatalog[ModelId.VAD]
        fakeCatalogFile(dir, spec, ByteArray(16))
        val reg = ModelRegistry(listOf(DirectoryModelSource(dir, "包")), tmp("state"))
        val e = assertFailsWith<CorruptModelException> { reg.resolve(ModelId.VAD) }
        assertTrue(e.message!!.contains("长度 16"), e.message!!)
    }

    @Test
    fun first_source_wins_so_a_pushed_override_beats_the_pack() {
        val over = tmp("over"); val pack = tmp("pack")
        val spec = ModelCatalog[ModelId.VAD]
        // Right length in both; only the path distinguishes them.
        fakeCatalogFile(over, spec, ByteArray(spec.bytes.toInt()) { 1 })
        fakeCatalogFile(pack, spec, ByteArray(spec.bytes.toInt()) { 2 })
        val reg = ModelRegistry(
            listOf(DirectoryModelSource(over, "override"), DirectoryModelSource(pack, "pack")),
            tmp("state"),
        )
        assertEquals(over.canonicalFile, reg.resolve(ModelId.VAD).parentFile.canonicalFile)
    }

    @Test
    fun a_full_length_file_with_wrong_bytes_only_fails_at_verify() {
        val dir = tmp("wrong")
        val spec = ModelCatalog[ModelId.VAD]
        fakeCatalogFile(dir, spec, ByteArray(spec.bytes.toInt()))
        val reg = ModelRegistry(listOf(DirectoryModelSource(dir, "包")), tmp("state"))
        reg.resolve(ModelId.VAD)   // length is right, so the cheap path passes
        val e = assertFailsWith<CorruptModelException> { reg.verify(ModelId.VAD) }
        assertTrue(e.message!!.contains("SHA-256"), e.message!!)
    }

    /** A registry over one small injected spec, so verify() can actually be run. */
    private fun tinyRegistry(dir: File, state: File, spec: ModelSpec) =
        ModelRegistry(listOf(DirectoryModelSource(dir, "包")), state) { spec }

    @Test
    fun verify_writes_a_marker_and_then_skips_rehashing() {
        val dir = tmp("ok"); val state = tmp("state")
        val content = ByteArray(4096) { (it % 7).toByte() }
        val spec = ModelSpec(ModelId.VAD, "fake.onnx", content.size.toLong(), sha256(content), "测试")
        val f = fakeCatalogFile(dir, spec, content)
        val marker = File(state, "fake.onnx.verified")

        assertFalse(marker.exists())
        tinyRegistry(dir, state, spec).verify(ModelId.VAD)
        assertTrue(marker.isFile, "marker must exist after a passing verify")
        assertEquals("${spec.sha256} ${f.length()} ${f.lastModified()}", marker.readText())

        // Second call must be satisfied by the marker. Proven by corrupting the
        // bytes in place, keeping length and mtime: the only way this can pass is
        // if no digest was computed.
        val at = f.lastModified()
        java.io.RandomAccessFile(f, "rw").use { raf -> raf.seek(0); raf.write(0xFF) }
        f.setLastModified(at)
        tinyRegistry(dir, state, spec).verify(ModelId.VAD)
    }

    @Test
    fun a_replaced_file_is_rehashed_rather_than_inheriting_the_verdict() {
        val dir = tmp("replace"); val state = tmp("state")
        val content = ByteArray(4096) { (it % 7).toByte() }
        val spec = ModelSpec(ModelId.VAD, "fake.onnx", content.size.toLong(), sha256(content), "测试")
        val f = fakeCatalogFile(dir, spec, content)
        tinyRegistry(dir, state, spec).verify(ModelId.VAD)

        // Same length, different bytes AND a new mtime — the realistic "re-fetched
        // and it came down wrong this time" case. The stale marker must not save it.
        f.writeBytes(ByteArray(content.size) { 1 })
        f.setLastModified(f.lastModified() + 2000)
        assertFailsWith<CorruptModelException> { tinyRegistry(dir, state, spec).verify(ModelId.VAD) }
    }

    @Test
    fun no_marker_is_left_behind_when_verification_fails() {
        val dir = tmp("fail"); val state = tmp("state")
        val content = ByteArray(4096) { 3 }
        val spec = ModelSpec(ModelId.VAD, "fake.onnx", content.size.toLong(), sha256(ByteArray(4096)), "测试")
        fakeCatalogFile(dir, spec, content)
        assertFailsWith<CorruptModelException> { tinyRegistry(dir, state, spec).verify(ModelId.VAD) }
        assertFalse(File(state, "fake.onnx.verified").exists(),
            "a failed verify that leaves a marker would pass forever after")
    }

    @Test
    fun verify_all_reports_cumulative_byte_progress() {
        val dir = tmp("all"); val state = tmp("state")
        val good = ByteArray(2048) { 5 }
        val spec = ModelSpec(ModelId.VAD, "fake.onnx", good.size.toLong(), sha256(good), "测试")
        fakeCatalogFile(dir, spec, good)
        val reg = tinyRegistry(dir, state, spec)

        val seen = ArrayList<Pair<Long, Long>>()
        reg.verifyAll(listOf(spec, spec)) { done, total -> seen.add(done to total) }
        assertEquals(listOf(2048L to 4096L, 4096L to 4096L), seen)
    }
}
