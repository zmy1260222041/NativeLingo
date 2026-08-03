package com.nativelingo.models

/**
 * Every model file the app needs, with the byte length and SHA-256 of the exact
 * artifact the device gates were measured against.
 *
 * **Cloud architecture (v0.7):** the Speaking track (transcription, MMS forced
 * alignment, FR-11 phoneme MDD) moved server-side, so whisper / Silero VAD /
 * MMS / espeak no longer ship in the APK. What remains is the 识物 module's
 * stack, which stays fully on-device: the SSL encoder (wav2vec2, reused by
 * FR-17 pronunciation scoring) and the YOLOE detector.
 *
 * **The hashes pin gate provenance, not just transport.** A truncated or
 * half-written file does not throw when ONNX Runtime opens it — it either fails
 * deep inside session creation with an unhelpful protobuf error, or (worse)
 * loads and produces garbage embeddings that flow into a calibrated score. So:
 * **updating a hash here means re-running that model's gate.** The same rule as
 * `:core-asr`'s `verifySherpaAar` pin (that module was removed with the cloud
 * migration, but the rule lives on).
 *
 * Sizes are bytes, deliberately, because the docs mix units: the model reviews
 * quote MiB (139.7 / 302.9) while other docs quote MB. [TOTAL_BYTES] is the
 * only figure that needs no unit footnote.
 */
enum class ModelId {
    /**
     * wav2vec2-base-960h layers 6-9, **fp16** with fp32 I/O and fp32 GELU (R-5).
     * Used by FR-17 pronunciation scoring (识物跟读) — reuses the same encoder
     * the Speaking track's SSL scoring used before it moved to the cloud.
     *
     * Was int8-transformer + fp32 CNN through the desktop gates, and the device
     * run is what changed it: on arm64 the int8 kernels put speaker invariance at
     * 0.18323 against R-5's ≤0.18 bar and the worst golden cosine at 0.98297
     * against ≥0.985 — both just past, both in the same direction, and no headroom
     * left to absorb a future export. fp16 measures 0.16917 and 0.990–0.997 on
     * the same device, i.e. better than macOS fp32's own 0.1714, so the shipped
     * criteria hold unchanged. The price is +43.9 MiB and half the encoder
     * throughput (21.6–25.2× → 12.2–12.8× realtime), which the user accepted
     * against a criteria rewrite. See docs/reviews/2026-07-26-android-device-first-run.md.
     */
    SSL_ENCODER,

    /**
     * YOLOE-26S-PF prompt-free detection export (detection-only; mask branch
     * stripped). The same ONNX bytes macOS uses for FR-13 — the Kotlin port in
     * `:core-vision` reads the identical file, so detection parity is a property
     * of the model artifact, not a re-export. Bundled and resident (45 MB; it
     * loads on first analyze and stays loaded). 识物 is deliberately NOT part of
     * the cloud migration (user decision): the photo stays on the device.
     */
    YOLOE_DETECT,
}

/**
 * @param fileName the name the file has on disk inside whichever source provides
 *   it. Flat, no subdirectories: an asset pack, an adb-pushed fixture directory
 *   and a sideload directory should not have to agree on a tree shape.
 * @param requiredBy which FR/module needs it — this is what a "model missing"
 *   error message shows the user, so it is product language, not module names.
 */
data class ModelSpec(
    val id: ModelId,
    val fileName: String,
    val bytes: Long,
    val sha256: String,
    val requiredBy: String,
)

object ModelCatalog {

    private val specs: Map<ModelId, ModelSpec> = listOf(
        ModelSpec(
            ModelId.SSL_ENCODER,
            "w2v2_base_69_fp16.onnx",
            146_472_265L,
            "eb271163fbb5d2dcfa8a9482abb5e6c9880150c8667ad21e1fa3c05da4465a68",
            "发音评分（识物跟读）",
        ),
        // FR-13 (识物) — YOLOE-26S-PF detection-only ONNX. The sha256 is the same
        // one macOS pins (model_assets.YOLO_SHA256); staging copies the file from
        // models/yoloe-26s-pf/ rather than build/onnx/, because it is an Ultralytics
        // export, not one of our quantized re-exports.
        ModelSpec(
            ModelId.YOLOE_DETECT,
            "yoloe-26s-pf.onnx",
            45_190_233L,
            "32866f4bb407805e4e94a7bc37634fd4e64e0d8349e69e7af3e93008f916a492",
            "看图识物",
        ),
    ).associateBy { it.id }

    operator fun get(id: ModelId): ModelSpec =
        specs[id] ?: error("no ModelSpec for $id — ModelCatalog is out of sync with ModelId")

    val all: List<ModelSpec> get() = ModelId.entries.map(::get)

    /**
     * What an install-time asset pack has to carry — with the Speaking models
     * gone to the server this is simply [all].
     */
    val installTime: List<ModelSpec> get() = all

    /** Bytes of [all] — 191,662,498 B = **182.8 MiB** (was 1034 MiB pre-cloud).
     * The APK drops from ~1 GB to ~270 MB total (models + piper clips + corpus). */
    val TOTAL_BYTES: Long = specs.values.sumOf { it.bytes }
}
