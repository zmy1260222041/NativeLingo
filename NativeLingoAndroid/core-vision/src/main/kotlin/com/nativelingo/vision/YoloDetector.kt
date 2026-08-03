package com.nativelingo.vision

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import android.graphics.Bitmap
import android.graphics.Color
import kotlin.math.ceil
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * YOLOE-26S-PF macro object detection for the Memorizing module (FR-13) — a
 * faithful Kotlin port of desktop/backend/core/vision.py.
 *
 * The model is the same prompt-free YOLOE detection-only ONNX export. Two model
 * passes cover the full recall range: a 640px whole-image pass for scene context
 * and large objects, then — for photos whose long edge is ≥1280px — overlapping
 * 1280px tiles that make small objects several times larger to the model.
 * Candidates from every pass are merged globally by confidence with cross-label
 * / cross-scale NMS (IoU 0.72 + nested-alias containment 0.82).
 *
 * The curated [LabelSpecs] table is the allowlist: a label absent from it can
 * never reach the UI. `person` is excluded by design (a photo covered in human
 * hotspots is hostile to a vocabulary surface).
 *
 * Output boxes are `[x, y, w, h]` in original-image pixels (1-decimal), matching
 * the desktop `/memorize/analyze` contract exactly — the same coordinates the
 * inspector and the click-crop math expect.
 *
 * @param modelPath absolute path to `yoloe-26s-pf.onnx` (resolved by ModelRegistry).
 */
class YoloDetector(modelPath: String) : AutoCloseable {

    /** A detection in original-image pixel coordinates, `box = [x, y, w, h]`. */
    data class Detection(
        val labelEn: String,
        val labelZh: String,
        val score: Float,
        val box: FloatArray,
        var id: Int = -1,
    )

    private val env: OrtEnvironment = OrtEnvironment.getEnvironment()
    private val session: OrtSession = env.createSession(modelPath, OrtSession.SessionOptions())
    private val inputName: String = session.inputNames.first()
    private val outputName: String = session.outputNames.first()

    /** Embedded YOLOE class vocabulary (id → English label), parsed from ONNX
     *  metadata `names`. ≥1200 labels expected for the real export. */
    private val names: Map<Int, String> = parseModelNames()
    private val labelSpecs: Map<String, LabelSpec> = LabelSpecs.load(names)

    /**
     * Detect curated whole objects in [bitmap] (already canonicalized — see
     * [MemorizeImageCodec]). Returns deduplicated detections, highest score
     * first, with stable sequential [Detection.id]s assigned post-NMS.
     */
    fun detect(
        bitmap: Bitmap,
        confidenceFloor: Float = 0f,
        dedupeIou: Float = DEDUPE_IOU,
        maxDet: Int = MAX_DET,
    ): List<Detection> {
        val origW = bitmap.width
        val origH = bitmap.height

        // 640px whole-image pass — scene context + large-object recall.
        val (wholeRaw, wholeGeo) = runPass(bitmap, IN_SIZE)
        val detections = parseOutput(
            wholeRaw, ratio = wholeGeo[0], padX = wholeGeo[1], padY = wholeGeo[2],
            origW = origW, origH = origH,
            confidenceFloor = confidenceFloor, dedupeIou = dedupeIou, maxDet = maxDet,
        ).toMutableList()

        // Overlapping 1280px tiles for small objects on large photos.
        if (maxOf(origW, origH) >= MULTISCALE_MIN_LONG_SIDE) {
            for (cropBox in multiscaleTiles(origW, origH)) {
                val cx1 = cropBox[0]; val cy1 = cropBox[1]
                val cx2 = cropBox[2]; val cy2 = cropBox[3]
                val tile = Bitmap.createBitmap(bitmap, cx1, cy1, cx2 - cx1, cy2 - cy1)
                val (tileRaw, tileGeo) = runPass(tile, MULTISCALE_IN_SIZE)
                val tileDets = parseOutput(
                    tileRaw, ratio = tileGeo[0], padX = tileGeo[1], padY = tileGeo[2],
                    origW = tile.width, origH = tile.height,
                    confidenceFloor = confidenceFloor, dedupeIou = dedupeIou, maxDet = maxDet,
                )
                if (tile !== bitmap) tile.recycle()
                for (td in tileDets) {
                    if (!multiscaleDetectionIsUsable(td)) continue
                    offsetCompleteDetection(td, cropBox, origW, origH)?.let { detections.add(it) }
                }
            }
        }

        return deduplicateDetections(detections, dedupeIou = dedupeIou, maxDet = maxDet)
    }

    override fun close() = session.close()

    // ── ONNX run ───────────────────────────────────────────────────────────────

    /** Run one dynamic-shape YOLOE pass at [newSize]. Returns the raw end-to-end
     *  output (`[N, 6]` rows of x1,y1,x2,y2,score,class in letterboxed px) plus
     *  the letterbox geometry `[ratio, padX, padY, inputW, inputH]`. */
    private fun runPass(bitmap: Bitmap, newSize: Int): Pair<Array<FloatArray>, FloatArray> {
        val (tensor, geo) = prepareTensor(bitmap, newSize)
        // ORT Java has no FloatArray+shape overload; the typed one takes a
        // FloatBuffer. tensor.data is already NCHW (channel-planar) float32 laid
        // out as [R-plane, G-plane, B-plane] by prepareTensor.
        val shape = longArrayOf(1, 3, tensor.h.toLong(), tensor.w.toLong())
        val onnx = OnnxTensor.createTensor(env, java.nio.FloatBuffer.wrap(tensor.data), shape)
        val raw: Array<FloatArray> = session.run(mapOf(inputName to onnx)).use { result ->
            @Suppress("UNCHECKED_CAST")
            (result.get(outputName).get().value as Array<Array<FloatArray>>)[0]
        }
        return raw to geo
    }

    /** Filter + un-letterbox the end-to-end output rows. Mirrors vision.py
     *  `_parse_output`: drop unknown labels, apply per-label min_score, un-pad/
     *  un-scale to original-image xywh, reject <2px boxes, then per-pass NMS. */
    private fun parseOutput(
        raw: Array<FloatArray>,
        ratio: Float,
        padX: Float,
        padY: Float,
        origW: Int,
        origH: Int,
        confidenceFloor: Float,
        dedupeIou: Float,
        maxDet: Int,
    ): List<Detection> {
        val candidates = ArrayList<Detection>()
        for (row in raw) {
            val score = row[4]
            val classId = row[5].roundToInt()
            val labelEn = names[classId] ?: continue
            val spec = labelSpecs[labelEn] ?: continue
            if (score < maxOf(spec.minScore, confidenceFloor)) continue

            val x1 = ((row[0] - padX) / ratio).coerceIn(0f, origW.toFloat())
            val y1 = ((row[1] - padY) / ratio).coerceIn(0f, origH.toFloat())
            val x2 = ((row[2] - padX) / ratio).coerceIn(0f, origW.toFloat())
            val y2 = ((row[3] - padY) / ratio).coerceIn(0f, origH.toFloat())
            val w = x2 - x1
            val h = y2 - y1
            if (w < 2f || h < 2f) continue
            candidates.add(
                Detection(
                    labelEn = labelEn,
                    labelZh = spec.zh,
                    score = round3(score),
                    box = floatArrayOf(round1(x1), round1(y1), round1(w), round1(h)),
                )
            )
        }
        return deduplicateDetections(candidates, dedupeIou = dedupeIou, maxDet = maxDet)
    }

    // ── model metadata ─────────────────────────────────────────────────────────

    private fun parseModelNames(): Map<Int, String> {
        val meta = session.metadata.customMetadata
        // These assertions guard against a wrong export slipping through (a
        // different Ultralytics version whose output differs silently). They
        // mirror vision.py `_load`.
        require(meta["end2end"] == "True") { "YOLOE ONNX is not the end-to-end detect export" }
        require(meta["task"] == "detect") { "YOLOE ONNX task != detect" }
        require(meta["native_lingo_proposal_conf"] == "0.10") { "unexpected YOLOE proposal threshold" }
        require(meta["native_lingo_max_det"] == "100") { "unexpected YOLOE candidate limit" }
        val raw = meta["names"] ?: error("YOLOE ONNX has no embedded class vocabulary")
        // `names` is a Python-dict-literal: "{0: 'person', 1: 'bicycle', ...}".
        val out = LinkedHashMap<Int, String>()
        val regex = Regex("""(\d+)\s*:\s*['"]([^'"]+)['"]""")
        for (m in regex.findAll(raw)) out[m.groupValues[1].toInt()] = m.groupValues[2]
        require(out.size >= MIN_VOCAB_SIZE) {
            "YOLOE vocabulary is unexpectedly small (${out.size} labels)"
        }
        return out
    }

    private companion object {
        const val IN_SIZE = 640
        const val MULTISCALE_IN_SIZE = 1280
        const val MULTISCALE_MIN_LONG_SIDE = 1280
        const val DEDUPE_IOU = 0.72f
        const val MAX_DET = 40
        const val STRIDE = 32
        const val PAD_GRAY = 114f / 255f
        const val MIN_VOCAB_SIZE = 1_200
        const val ALIAS_CONTAINMENT_THRESHOLD = 0.82f
        const val MULTISCALE_OVERLAP = 0.5f
        const val MULTISCALE_EDGE_MARGIN_RATIO = 0.005f
    }
}

// ════════════════════════════════════════════════════════════════════════════
// Pure geometry helpers — top-level so JVM unit tests can exercise the letterbox
// / IoU / NMS math without an ONNX session or a Bitmap (no Android runtime).
// These mirror desktop/backend/core/vision.py function-for-function.
// ════════════════════════════════════════════════════════════════════════════

internal const val LETTERBOX_STRIDE = 32
internal const val LETTERBOX_PAD_GRAY = 114f / 255f

/** Letterbox transform: longest side → [newSize], shorter side padded to the next
 *  stride multiple. Returns `[ratio, padX, padY, inputW, inputH]`. */
internal fun letterbox(width: Int, height: Int, newSize: Int, stride: Int): FloatArray {
    val ratio = min(newSize.toFloat() / width, newSize.toFloat() / height)
    val resizedW = max(1, (width * ratio).roundToInt())
    val resizedH = max(1, (height * ratio).roundToInt())
    val inputW = min(newSize, ceil(resizedW.toFloat() / stride).toInt() * stride)
    val inputH = min(newSize, ceil(resizedH.toFloat() / stride).toInt() * stride)
    val padX = (((inputW - resizedW) / 2f) - 0.1f).roundToInt()
    val padY = (((inputH - resizedH) / 2f) - 0.1f).roundToInt()
    return floatArrayOf(ratio, padX.toFloat(), padY.toFloat(), inputW.toFloat(), inputH.toFloat())
}

/** (H, W, 3) → NCHW float buffer laid out as three channel planes
 *  (R[h*w], G[h*w], B[h*w]). The YOLOE ONNX expects NCHW; OnnxTensor gets a
 *  FloatBuffer view of [data] with shape [1, 3, h, w]. */
internal class FloatImage(val h: Int, val w: Int) {
    val data = FloatArray(h * w * 3)
}

/** Bilinear-resize [bitmap] onto a stride-aligned gray (114) canvas and return
 *  the NCHW float buffer plus the letterbox geometry for un-padding. */
internal fun prepareTensor(bitmap: Bitmap, newSize: Int): Pair<FloatImage, FloatArray> {
    val geo = letterbox(bitmap.width, bitmap.height, newSize, LETTERBOX_STRIDE)
    val ratio = geo[0]; val padX = geo[1].toInt(); val padY = geo[2].toInt()
    val inputW = geo[3].toInt(); val inputH = geo[4].toInt()
    val resizedW = max(1, (bitmap.width * ratio).roundToInt())
    val resizedH = max(1, (bitmap.height * ratio).roundToInt())
    val scaled = if (resizedW == bitmap.width && resizedH == bitmap.height) bitmap
        else Bitmap.createScaledBitmap(bitmap, resizedW, resizedH, true)
    val out = FloatImage(inputH, inputW)
    // Default the whole canvas to the gray pad, all three planes.
    for (i in out.data.indices) out.data[i] = LETTERBOX_PAD_GRAY
    val planeSize = inputW * inputH
    for (y in 0 until resizedH) {
        for (x in 0 until resizedW) {
            val px = scaled.getPixel(x, y)
            // NCHW: pixel (x,y) of channel c lives at [c*planeSize + (y*inputW + x)].
            val pos = (y + padY) * inputW + (x + padX)
            out.data[pos] = Color.red(px) / 255f
            out.data[planeSize + pos] = Color.green(px) / 255f
            out.data[2 * planeSize + pos] = Color.blue(px) / 255f
        }
    }
    return out to floatArrayOf(ratio, padX.toFloat(), padY.toFloat(), inputW.toFloat(), inputH.toFloat())
}

/** IoU between two xywh boxes. */
internal fun boxIou(a: FloatArray, b: FloatArray): Float {
    val ax1 = a[0]; val ay1 = a[1]; val aw = a[2]; val ah = a[3]
    val bx1 = b[0]; val by1 = b[1]; val bw = b[2]; val bh = b[3]
    val ax2 = ax1 + aw; val ay2 = ay1 + ah
    val bx2 = bx1 + bw; val by2 = by1 + bh
    val inter = max(0f, min(ax2, bx2) - max(ax1, bx1)) * max(0f, min(ay2, by2) - max(ay1, by1))
    return inter / (aw * ah + bw * bh - inter + 1e-9f)
}

/** Containment: intersection / smaller-area, for nested alias boxes. */
internal fun boxContainment(a: FloatArray, b: FloatArray): Float {
    val ax1 = a[0]; val ay1 = a[1]; val aw = a[2]; val ah = a[3]
    val bx1 = b[0]; val by1 = b[1]; val bw = b[2]; val bh = b[3]
    val ax2 = ax1 + aw; val ay2 = ay1 + ah
    val bx2 = bx1 + bw; val by2 = by1 + bh
    val inter = max(0f, min(ax2, bx2) - max(ax1, bx1)) * max(0f, min(ay2, by2) - max(ay1, by1))
    return inter / (min(aw * ah, bw * bh) + 1e-9f)
}

/** True when one label's word-set subsumes the other (mug⊆coffee mug, sofa⊆couch). */
internal fun labelsAreNestedAliases(first: String, second: String): Boolean {
    // Kotlin's Set has no Python-style `<=` for subset — use containsAll.
    val a = first.split(' ').toSet()
    val b = second.split(' ').toSet()
    return (a.isNotEmpty() && b.containsAll(a)) || (b.isNotEmpty() && a.containsAll(b))
}

/** Global cross-label / cross-scale NMS; assigns stable sequential ids. */
internal fun deduplicateDetections(
    candidates: List<YoloDetector.Detection>,
    dedupeIou: Float,
    maxDet: Int,
    aliasContainment: Float = 0.82f,
): List<YoloDetector.Detection> {
    val sorted = candidates.sortedByDescending { it.score }
    val kept = ArrayList<YoloDetector.Detection>()
    for (cand in sorted) {
        val suppressed = kept.any { prior ->
            boxIou(cand.box, prior.box) >= dedupeIou ||
                (labelsAreNestedAliases(cand.labelEn, prior.labelEn) &&
                    boxContainment(cand.box, prior.box) >= aliasContainment)
        }
        if (suppressed) continue
        kept.add(cand)
        if (kept.size >= maxDet) break
    }
    kept.forEachIndexed { i, d -> d.id = i }
    return kept
}

/** Overlapping square tile crop boxes covering the full image. */
internal fun multiscaleTiles(
    width: Int,
    height: Int,
    tileRatio: Float = 5f / 12f,
    overlap: Float = 0.5f,
): List<IntArray> {
    val tileLen = max(1, (max(width, height) * tileRatio).roundToInt())
    val xTiles = tileAxis(width, tileLen, overlap)
    val yTiles = tileAxis(height, tileLen, overlap)
    val out = ArrayList<IntArray>(xTiles.size * yTiles.size)
    for ((x1, x2) in xTiles) for ((y1, y2) in yTiles) out.add(intArrayOf(x1, y1, x2, y2))
    return out
}

/** Overlapping (start, end) intervals covering one axis. */
internal fun tileAxis(length: Int, tileLen: Int, overlap: Float): List<Pair<Int, Int>> {
    val t = min(length, tileLen)
    if (t >= length) return listOf(0 to length)
    val step = max(1, (t * (1f - overlap)).roundToInt())
    val lastStart = length - t
    val starts = (0..lastStart step step).toMutableList()
    if (starts.last() != lastStart) starts.add(lastStart)
    return starts.map { it to it + t }
}

/** Geometry rule for magnified-tile candidates (plaque aspect gate). */
private fun multiscaleDetectionIsUsable(d: YoloDetector.Detection): Boolean {
    if (d.labelEn == "plaque") {
        val w = d.box[2]; val h = d.box[3]
        val aspect = w / max(h, 1e-9f)
        return aspect >= 1.6f && aspect <= 2.5f
    }
    return true
}

/** Map a tile-local detection back to full-image coords; reject boxes clipped by
 *  internal tile edges (source-image edges stay eligible). Returns null on reject. */
private fun offsetCompleteDetection(
    d: YoloDetector.Detection,
    cropBox: IntArray,
    imageW: Int,
    imageH: Int,
    edgeMarginRatio: Float = 0.005f,
): YoloDetector.Detection? {
    val cx1 = cropBox[0]; val cy1 = cropBox[1]; val cx2 = cropBox[2]; val cy2 = cropBox[3]
    val cropW = cx2 - cx1; val cropH = cy2 - cy1
    val x = d.box[0]; val y = d.box[1]; val w = d.box[2]; val h = d.box[3]
    val margin = max(2f, max(cropW, cropH).toFloat() * edgeMarginRatio)
    if ((cx1 > 0 && x <= margin) ||
        (cy1 > 0 && y <= margin) ||
        (cx2 < imageW && x + w >= cropW - margin) ||
        (cy2 < imageH && y + h >= cropH - margin)
    ) return null
    return d.copy(box = floatArrayOf(round1(x + cx1), round1(y + cy1), w, h))
}

private fun round1(v: Float): Float = (v * 10f).roundToInt() / 10f
private fun round3(v: Float): Float = (v * 1000f).roundToInt() / 1000f
