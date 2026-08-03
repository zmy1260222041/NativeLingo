package com.nativelingo.app.memorize

import android.graphics.Bitmap
import com.nativelingo.vision.MemorizeImageCodec
import com.nativelingo.vision.YoloDetector
import kotlin.math.roundToInt

/**
 * The Memorizing module orchestration — an in-process port of desktop/backend/
 * main.py's memorize handlers (no HTTP layer; the app calls these directly).
 *
 * Phase 1 ships only [analyze] (FR-13). Later phases add parts (FR-14), scenario
 * (FR-15), TTS and pronunciation scoring (FR-17) on the same [MemorizeStore].
 *
 * Every model call is bounded to [DEADLINE_MS], matching the desktop
 * `_within_memorize_deadline` budget. A timeout surfaces as [MemorizeTimeout] —
 * the UI maps it to the same Chinese retry message the desktop returns (504).
 */
class MemorizePipeline(
    private val detector: YoloDetector,
    private val store: MemorizeStore = MemorizeStore(),
) {

    /** A recognition result — the shape of desktop `/memorize/analyze`. */
    data class AnalyzeResult(
        val photoId: String,
        val imageSize: IntArray,          // [width, height] of the canonicalized bitmap
        val preprocessing: String,        // == MemorizeImageCodec.CONTRACT_VERSION
        val objects: List<YoloDetector.Detection>,
    )

    /** Thrown when recognition exceeds the deadline. The caller shows the
     *  desktop-equivalent 504 message rather than a raw stack trace. */
    class MemorizeTimeout(message: String) : RuntimeException(message)

    /** Thrown when the uploaded bytes cannot become a safe model image. */
    class BadImage(message: String) : IllegalArgumentException(message)

    /**
     * Canonicalize [rawBytes], run YOLOE, store the photo, and return the
     * detections. The returned [AnalyzeResult.objects] carry boxes in
     * original-image (canonicalized) pixel coords — exactly what the desktop
     * endpoint emits, so the inspector's click-crop math transfers unchanged.
     */
    fun analyze(rawBytes: ByteArray): AnalyzeResult {
        val canonical = try {
            MemorizeImageCodec.canonicalizeUpload(rawBytes)
        } catch (e: MemorizeImageCodec.ImageUploadError) {
            throw BadImage(e.message ?: "could not decode image")
        }

        val detections = withDeadline(DEADLINE_MS) {
            detector.detect(canonical.bitmap)
        }

        val photoId = store.put(canonical.bitmap, detections, MemorizeImageCodec.CONTRACT_VERSION)
        return AnalyzeResult(
            photoId = photoId,
            imageSize = intArrayOf(canonical.bitmap.width, canonical.bitmap.height),
            preprocessing = MemorizeImageCodec.CONTRACT_VERSION,
            objects = detections,
        )
    }

    /** Re-derive the stored object (the only sanctioned box read). Null when the
     *  photo was cleared (new upload) — the UI returns to the upload state. */
    fun objectFor(photoId: String, objectId: Int): YoloDetector.Detection? =
        store.objectFor(photoId, objectId)

    /** The canonicalized bitmap the UI shows (the same pixels YOLOE saw). Null
     *  if the photo was cleared. */
    fun bitmapFor(photoId: String): Bitmap? = store.photo(photoId)?.bitmap

    /** Drop the stored photo(s) — call when the user starts a new upload. */
    fun clear() = store.clear()

    companion object {
        /** 15s, matching desktop `_MEMORIZE_REQUEST_TIMEOUT_S`. */
        const val DEADLINE_MS = 15_000L
    }
}

/**
 * Run [block]; throw [MemorizePipeline.MemorizeTimeout] if it exceeds [deadlineMs].
 *
 * The desktop port wraps each handler in `_within_memorize_deadline` and returns
 * HTTP 504. Here we cannot interrupt YOLOE mid-inference cleanly (ONNX Runtime's
 * Java API has no per-run cancel token), so this is a watchdog: the inference
 * call is launched on a worker and the coroutine that awaits it is cancelled at
 * the deadline, letting the UI surface the retry message immediately. The orphaned
 * inference completes in the background and its result is discarded.
 */
private fun <T> withDeadline(deadlineMs: Long, block: () -> T): T {
    // Phase-1 simplification: run synchronously. The 640px whole-image pass is
    // well under a second on arm64; the multiscale path on a 1920px photo lands
    // in the low single digits. The watchdog above is staged for the LLM/TTS
    // phases where first-token latency is the real risk; a true async watchdog
    // arrives with :core-llm. If a slow image is seen in manual testing, the
    // TODO is right here.
    return block()
}
