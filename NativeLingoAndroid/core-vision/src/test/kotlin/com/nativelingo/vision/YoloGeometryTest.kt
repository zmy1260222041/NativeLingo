package com.nativelingo.vision

import com.nativelingo.vision.YoloDetector.Detection
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Pure-geometry parity tests for the YOLOE port — the letterbox / IoU /
 * containment / NMS / tiling math, verified without a model or a Bitmap on the
 * JVM (the same split :core-embed uses). These functions mirror
 * desktop/backend/core/vision.py function-for-function; the assertions pin the
 * numerical behavior the desktop port relies on:
 *
 *  - letterbox keeps the long edge at the target and pads the short edge to a
 *    stride multiple, with the −0.1 pad bias the Python port has;
 *  - IoU and containment match the formulae used by the cross-label / cross-scale
 *    dedup (0.72 IoU and 0.82 alias-containment gates);
 *  - dedup keeps the highest-scoring box and suppresses both high-IoU duplicates
 *    and nested-alias overlaps, assigning stable sequential ids.
 */
class YoloGeometryTest {

    // ── letterbox ──────────────────────────────────────────────────────────────

    @Test fun letterbox_scales_long_edge_to_target_and_aligns_short_to_stride() {
        // 1920×1080 → 640 target: ratio 1/3, resized 640×360.
        // inputW=640 (already stride-aligned), inputH=ceil(360/32)*32=384.
        // padX=(640−640)/2−0.1 → −0.1 → 0 (width already fills). padY=(384−360)/2−0.1 → 11.9 → 12.
        val g = letterbox(1920, 1080, 640, 32)  // [ratio, padX, padY, inputW, inputH]
        assertEquals(1f / 3f, g[0], 1e-5f)
        assertEquals(0f, g[1], 1e-3f)     // width fills the canvas → no x pad
        assertEquals(12f, g[2], 1e-3f)    // height centered with the −0.1 bias
        assertEquals(640f, g[3], 1e-3f)
        assertEquals(384f, g[4], 1e-3f)
    }

    @Test fun letterbox_portrait_keeps_height_as_long_edge() {
        val g = letterbox(1080, 1920, 640, 32)
        assertEquals(1f / 3f, g[0], 1e-5f)
        assertEquals(384f, g[3], 1e-3f)
        assertEquals(640f, g[4], 1e-3f)
    }

    @Test fun letterbox_small_image_is_upscaled_to_target() {
        // 320×240 → target 640: ratio = min(640/320, 640/240) = min(2, 2.67) = 2.
        // The Python port scales UP (no clamp at 1.0) — a small upload is enlarged,
        // which is fine because MemorizeImageCodec caps the long edge at 1920 first,
        // so real inputs are >= 640 on the long side in practice.
        val g = letterbox(320, 240, 640, 32)
        assertEquals(2f, g[0], 1e-5f)
        assertEquals(640f, g[3], 1e-3f)
        assertEquals(480f, g[4], 1e-3f)  // 240*2=480, already stride-aligned
    }

    // ── IoU & containment ─────────────────────────────────────────────────────

    @Test fun iou_identical_boxes_is_one() {
        val b = floatArrayOf(10f, 10f, 20f, 20f)
        assertEquals(1f, boxIou(b, b), 1e-4f)
    }

    @Test fun iou_disjoint_boxes_is_zero() {
        val a = floatArrayOf(0f, 0f, 10f, 10f)
        val b = floatArrayOf(100f, 100f, 10f, 10f)
        assertEquals(0f, boxIou(a, b), 1e-6f)
    }

    @Test fun iou_half_overlap_known_value() {
        // Two 10×10 boxes offset by 5 on x: intersection 5×10=50, union 100+100−50=150
        val a = floatArrayOf(0f, 0f, 10f, 10f)
        val b = floatArrayOf(5f, 0f, 10f, 10f)
        assertEquals(50f / 150f, boxIou(a, b), 1e-4f)
    }

    @Test fun containment_nested_box_is_one() {
        // A small box entirely inside a large one: intersection/small = 1
        val big = floatArrayOf(0f, 0f, 100f, 100f)
        val small = floatArrayOf(10f, 10f, 10f, 10f)
        assertEquals(1f, boxContainment(big, small), 1e-4f)
        assertEquals(1f, boxContainment(small, big), 1e-4f)
    }

    // ── nested alias labels ───────────────────────────────────────────────────

    @Test fun nested_aliases_match_word_subset() {
        assertTrue(labelsAreNestedAliases("mug", "coffee mug"))
        assertTrue(labelsAreNestedAliases("coffee mug", "mug"))
        assertTrue(labelsAreNestedAliases("couch", "sofa couch"))
    }

    @Test fun unrelated_labels_are_not_aliases() {
        assertFalse(labelsAreNestedAliases("mug", "cup"))
        assertFalse(labelsAreNestedAliases("bicycle", "car"))
    }

    // ── deduplication / NMS ───────────────────────────────────────────────────

    @Test fun dedup_keeps_highest_score_and_assigns_ids() {
        val candidates = listOf(
            det("mug", 0.9f, floatArrayOf(0f, 0f, 10f, 10f)),
            det("mug", 0.5f, floatArrayOf(0f, 0f, 10f, 10f)),  // identical → suppressed
        )
        val out = deduplicateDetections(candidates, dedupeIou = 0.72f, maxDet = 40)
        assertEquals(1, out.size)
        assertEquals(0.9f, out[0].score)
        assertEquals(0, out[0].id)
    }

    @Test fun dedup_suppresses_nested_alias_overlap() {
        // "mug" inside "coffee mug" at 0.9 containment — alias rule suppresses the
        // lower-scoring one even though IoU < 0.72.
        val big = det("coffee mug", 0.8f, floatArrayOf(0f, 0f, 100f, 100f))
        val small = det("mug", 0.6f, floatArrayOf(40f, 40f, 20f, 20f))  // fully inside
        val out = deduplicateDetections(listOf(big, small), dedupeIou = 0.72f, maxDet = 40)
        assertEquals(1, out.size)
        assertEquals("coffee mug", out[0].labelEn)
    }

    @Test fun dedup_keeps_distinct_objects() {
        val a = det("mug", 0.9f, floatArrayOf(0f, 0f, 10f, 10f))
        val b = det("laptop", 0.85f, floatArrayOf(200f, 200f, 50f, 40f))
        val out = deduplicateDetections(listOf(a, b), dedupeIou = 0.72f, maxDet = 40)
        assertEquals(2, out.size)
    }

    @Test fun dedup_respects_max_det() {
        val candidates = (1..50).map { det("obj$it", 0.5f + it * 0.001f, floatArrayOf(it * 10f, 0f, 5f, 5f)) }
        assertEquals(40, deduplicateDetections(candidates, dedupeIou = 0.72f, maxDet = 40).size)
    }

    // ── multiscale tiling ─────────────────────────────────────────────────────

    @Test fun tile_axis_covers_full_length_when_tile_ge_length() {
        assertEquals(listOf(0 to 100), tileAxis(100, 200, 0.5f))
    }

    @Test fun tile_axis_overlaps_with_half_step() {
        // length 1000, tile 100, overlap 0.5 → step 50; last start 900.
        val tiles = tileAxis(1000, 100, 0.5f)
        assertEquals(0, tiles.first().first)
        assertEquals(1000, tiles.last().second)
        assertTrue(tiles.any { it.first == 900 }, "expected a tile starting at the last-start")
        // consecutive tiles overlap by ~50
        val (a, b) = tiles[0] to tiles[1]
        assertEquals(50, b.first - a.first)
    }

    @Test fun multiscale_tiles_are_square_and_cover_the_full_image() {
        val tiles = multiscaleTiles(1920, 1080)
        // Tile count isn't monotonic in image size (it depends on aspect ratio),
        // so assert coverage instead: the union of tile spans reaches every edge.
        val minX = tiles.minOf { it[0] }; val maxX = tiles.maxOf { it[2] }
        val minY = tiles.minOf { it[1] }; val maxY = tiles.maxOf { it[3] }
        assertEquals(0, minX)
        assertEquals(0, minY)
        assertEquals(1920, maxX)
        assertEquals(1080, maxY)
        // Every tile is square with side ≈ 5/12 of the long edge (1920).
        val expectedTileLen = (1920 * 5f / 12f).toInt()
        for (t in tiles) assertEquals(expectedTileLen, t[2] - t[0])
        assertEquals(expectedTileLen, tiles.first()[3] - tiles.first()[1])
    }

    private fun det(label: String, score: Float, box: FloatArray) = Detection(label, "译", score, box)
}
