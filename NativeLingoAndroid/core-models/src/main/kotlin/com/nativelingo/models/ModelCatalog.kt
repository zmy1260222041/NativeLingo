package com.nativelingo.models

/**
 * Every model file the app needs, with the byte length and SHA-256 of the exact
 * artifact the Phase-0 gates were measured against.
 *
 * **The hashes pin gate provenance, not just transport.** A truncated or
 * half-written 338 MiB download does not throw when ONNX Runtime opens it — it
 * either fails deep inside session creation with an unhelpful protobuf error, or
 * (worse) loads and produces garbage embeddings that flow into a calibrated
 * score. But that is only half the point: these bytes are *the* bytes R-5/R-6/
 * R-7/R-10 passed on. `quantize_dynamic` is not guaranteed bit-reproducible
 * across ORT versions, so re-running an export script legitimately changes a
 * hash — and when it does, the gate result no longer describes the shipped file.
 * So: **updating a hash here means re-running that model's gate.** The same rule
 * as `:core-asr`'s `verifySherpaAar` pin.
 *
 * Sizes are bytes, deliberately, because the docs mix units: the model reviews
 * quote MiB (139.7 / 338.6 / 302.9) while R-10 quotes whisper in MB (159.8 =
 * 152.4 MiB). [TOTAL_BYTES] is the only figure that needs no unit footnote.
 */
enum class ModelId {
    /**
     * wav2vec2-base-960h layers 6-9, **fp16** with fp32 I/O and fp32 GELU (R-5).
     * FR-4/FR-5.
     *
     * Was int8-transformer + fp32 CNN through the desktop gates, and the device
     * run is what changed it: on arm64 the int8 kernels put speaker invariance at
     * 0.18323 against R-5's ≤0.18 bar and the worst golden cosine at 0.98297
     * against ≥0.985 — both just past, both in the same direction, and no headroom
     * left to absorb a future export. fp16 measures 0.16917 and 0.990–0.997 on
     * the same device, i.e. better than macOS fp32's own 0.1714, so the shipped
     * criteria hold unchanged. The price is +43.9 MiB and half the encoder
     * throughput (21.6–25.2× → 12.2–12.8× realtime; ranges because emulator wall-clock
     * jitters ±15%, ratio stable at 1.8–2.0×), which the user accepted against a
     * criteria rewrite. See docs/reviews/2026-07-26-android-device-first-run.md.
     */
    SSL_ENCODER,

    /** MMS_FA re-hosted on HF Wav2Vec2ForCTC, int8 transformer (R-6). FR-2/FR-6/FR-8. */
    MMS_ALIGNER,

    /** wav2vec2-lv-60-espeak-cv-ft, full int8 (R-7). FR-11 — loaded lazily, Phase 3. */
    ESPEAK_MDD,

    /** Silero VAD — speech spans for whisper windowing (R-10) and FR-3 liveness. */
    VAD,

    WHISPER_BASE_EN_ENCODER,
    WHISPER_BASE_EN_DECODER,
    WHISPER_BASE_EN_TOKENS,

    WHISPER_TINY_EN_ENCODER,
    WHISPER_TINY_EN_DECODER,
    WHISPER_TINY_EN_TOKENS,
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

/**
 * Whisper tier (R-11).
 *
 * Two tiers ship, and which one is default is a decision with a paper trail:
 * [BASE_EN] is the release tier, [TINY_EN] is a *speed* fallback for slow
 * devices — 1.67× faster (636 s of audio: 38.2 s → 22.9 s on desktop), and
 * 57 MB smaller, but its transcription errors are structurally worse, not just
 * more frequent. tiny.en emits non-words (`terror-frueling`, `infatically`);
 * MMS forced alignment has no reject path, so it must spread characters that
 * were never spoken across real audio, and FR-2/FR-6/FR-8 lose correspondence
 * over that span. base.en's divergences are all real English words in the right
 * place. So tiny.en is never a size lever — only a latency one, and only where
 * base.en is measured to be too slow.
 *
 * The threshold for "too slow" is deliberately not encoded here: it needs
 * device data (R-11 §没做的事).
 *
 * See docs/reviews/2026-07-26-android-r11-whisper-tier.md.
 */
enum class WhisperTier(
    val encoder: ModelId,
    val decoder: ModelId,
    val tokens: ModelId,
) {
    BASE_EN(
        ModelId.WHISPER_BASE_EN_ENCODER,
        ModelId.WHISPER_BASE_EN_DECODER,
        ModelId.WHISPER_BASE_EN_TOKENS,
    ),
    TINY_EN(
        ModelId.WHISPER_TINY_EN_ENCODER,
        ModelId.WHISPER_TINY_EN_DECODER,
        ModelId.WHISPER_TINY_EN_TOKENS,
    ),
    ;

    val ids: List<ModelId> get() = listOf(encoder, decoder, tokens)

    companion object {
        /** NFR-4②: base.en ships as the default; tiny.en is opt-in per device. */
        val DEFAULT = BASE_EN
    }
}

object ModelCatalog {

    private val specs: Map<ModelId, ModelSpec> = listOf(
        ModelSpec(
            ModelId.SSL_ENCODER,
            "w2v2_base_69_fp16.onnx",
            146_472_265L,
            "eb271163fbb5d2dcfa8a9482abb5e6c9880150c8667ad21e1fa3c05da4465a68",
            "发音准确度与流畅度评分",
        ),
        ModelSpec(
            ModelId.MMS_ALIGNER,
            "mms_fa_int8_transformer.onnx",
            355_076_269L,
            "ebe564510025752ed340873d897fda413aa8dc63db373868da9890eb917af6bd",
            "词级定位与 A/B 回放",
        ),
        ModelSpec(
            ModelId.ESPEAK_MDD,
            "espeak_cv_ft_int8.onnx",
            317_746_568L,
            "f0ba636f5786c73b929a7a493069c7f4e7531c07c5e1c5b60afa70eb083e1a93",
            "音素级诊断",
        ),
        ModelSpec(
            ModelId.VAD,
            "silero_vad.onnx",
            643_854L,
            "9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6",
            "转写切窗与录音检测",
        ),
        ModelSpec(
            ModelId.WHISPER_BASE_EN_ENCODER,
            "base.en-encoder.int8.onnx",
            29_120_534L,
            "ef6b936f4c9b1d90a3b68634b60c4ed8576b26172b33c2535ec0e933c9edb823",
            "视频转写",
        ),
        ModelSpec(
            ModelId.WHISPER_BASE_EN_DECODER,
            "base.en-decoder.int8.onnx",
            130_669_978L,
            "f7162ad6db2dbef16cfaeaa7f945b9d7dd9c1b8d472f6aca82f2273d185e4d41",
            "视频转写",
        ),
        ModelSpec(
            ModelId.WHISPER_BASE_EN_TOKENS,
            "base.en-tokens.txt",
            835_554L,
            "306cd27f03c1a714eca7108e03d66b7dc042abe8c258b44c199a7ed9838dd930",
            "视频转写",
        ),
        ModelSpec(
            ModelId.WHISPER_TINY_EN_ENCODER,
            "tiny.en-encoder.int8.onnx",
            12_937_772L,
            "0ce578b827c94a961aacb8fa14b02f096504b337e5c94be37c36238cbe3e8bc6",
            "视频转写(低端设备降级档)",
        ),
        ModelSpec(
            ModelId.WHISPER_TINY_EN_DECODER,
            "tiny.en-decoder.int8.onnx",
            89_853_865L,
            "06c0e6ff6348d427e51839219d1c886c18cfdf411e629e33f5e1679bff9c1527",
            "视频转写(低端设备降级档)",
        ),
        // Same file as base.en's, byte for byte — both tiers use the multilingual
        // 51864-token vocabulary. Kept as a separate entry rather than aliased so
        // a tier is self-describing and a future tier with its own vocabulary
        // (a multilingual model, say) does not need the catalog restructured.
        ModelSpec(
            ModelId.WHISPER_TINY_EN_TOKENS,
            "tiny.en-tokens.txt",
            835_554L,
            "306cd27f03c1a714eca7108e03d66b7dc042abe8c258b44c199a7ed9838dd930",
            "视频转写(低端设备降级档)",
        ),
    ).associateBy { it.id }

    operator fun get(id: ModelId): ModelSpec =
        specs[id] ?: error("no ModelSpec for $id — ModelCatalog is out of sync with ModelId")

    val all: List<ModelSpec> get() = ModelId.entries.map(::get)

    /**
     * What an install-time asset pack has to carry: everything except the
     * tiny.en tier, which is not the release default and would otherwise cost
     * 98 MiB of install size for a fallback most devices never take.
     *
     * FR-11's espeak model IS included even though it is loaded lazily — lazily
     * means "not held in RAM until a weak/bad word appears", not "fetched later".
     * Downloading 303 MiB at the moment a learner asks why a word sounded wrong
     * would be the worst possible time.
     */
    val installTime: List<ModelSpec> get() = all.filter { it.id !in WhisperTier.TINY_EN.ids }

    /** Bytes of [all], both whisper tiers included — 1,084,192,213 B = 1034.0 MiB. */
    val TOTAL_BYTES: Long = specs.values.sumOf { it.bytes }

    /**
     * Bytes of [installTime] — 980,565,022 B = **935.1 MiB**, up from 891.3 MiB
     * when [ModelId.SSL_ENCODER] moved from the int8 export to fp16 after the
     * device run. Still inside an asset pack's 1.5 GB ceiling with 590 MiB to
     * spare, and still past the base-APK ceiling several times over, so nothing
     * about the delivery mechanism changes — which is why +43.9 MiB was the whole
     * of that decision's cost besides throughput.
     */
    val INSTALL_TIME_BYTES: Long = installTime.sumOf { it.bytes }
}
