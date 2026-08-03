package com.nativelingo.app.gates

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nativelingo.models.ModelId
import com.nativelingo.vision.YoloDetector
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.test.assertTrue

/**
 * Device-side smoke gate for the YOLOE port (FR-13) — verifies the ONNX model
 * loads and runs end-to-end on arm64 with `onnxruntime-android` (the XNNPACK
 * kernel build that actually ships, not the macOS JVM build the unit test uses),
 * and that detections are structurally well-formed.
 *
 * This is a smoke gate, not a parity gate: a synthetic bitmap rarely triggers
 * the curated vocabulary at threshold, so we assert the pipeline runs in budget
 * and returns well-formed boxes (not that it finds specific objects). Numerical
 * parity against the macOS golden detections is staged for when
 * `scripts/capture_memorize_golden.py` ships a real-photo fixture + JSON — the
 * same pattern the SSL/aligner gates follow.
 *
 * Budget: the whole-image 640px pass must finish well under the 15s Memorizing
 * deadline; we assert 10s headroom for the emulator's slower kernels.
 */
@RunWith(AndroidJUnit4::class)
class YoloDetectorDeviceTest {

    @Test
    fun model_loads_and_detect_runs_in_budget() {
        val modelFile = DeviceFixtures.requireModel(ModelId.YOLOE_DETECT)
        DeviceFixtures.logPresentModels()

        // A 640×480 bitmap with two colored rectangles on a gray field — enough
        // texture for the ONNX run to exercise the full letterbox → infer → parse
        // path without depending on a real-photo asset the test APK doesn't carry.
        val bitmap = Bitmap.createBitmap(640, 480, Bitmap.Config.ARGB_8888).apply {
            val canvas = Canvas(this)
            canvas.drawColor(Color.rgb(114, 114, 114))
            val paint = Paint().apply { isAntiAlias = false }
            paint.color = Color.rgb(200, 50, 50)
            canvas.drawRect(50f, 50f, 250f, 350f, paint)
            paint.color = Color.rgb(50, 50, 200)
            canvas.drawRect(350f, 100f, 600f, 400f, paint)
        }

        YoloDetector(modelFile.absolutePath).use { detector ->
            val start = SystemClock.elapsedRealtime()
            val detections = detector.detect(bitmap)
            val elapsed = SystemClock.elapsedRealtime() - start

            assertTrue(elapsed < 10_000, "detect took ${elapsed}ms on arm64 (budget 10s)")

            // Structural checks on whatever came back (may be empty for a synthetic image).
            for (d in detections) {
                assertTrue(d.score in 0f..1f, "score out of range: ${d.score}")
                assertTrue(d.labelEn.isNotEmpty(), "empty label")
                assertTrue(d.labelZh.isNotEmpty(), "empty zh label")
                assertTrue(d.box.size == 4, "box must be xywh")
                assertTrue(d.box[2] > 0f && d.box[3] > 0f, "non-positive box size: ${d.box.toList()}")
                assertTrue(d.box[0] >= 0f && d.box[1] >= 0f, "negative box origin: ${d.box.toList()}")
                assertTrue(d.id >= 0, "unassigned id: ${d.id}")
            }
            // ids are 0..n-1 sequential post-NMS.
            detections.sortedBy { it.id }.forEachIndexed { i, d -> assertTrue(d.id == i, "id not sequential") }
        }
    }

    @Test
    fun large_image_multiscale_path_runs_in_budget() {
        // A 1920×1080 bitmap (at the canonicalize cap) exercises the overlapping
        // 1280px tile path on top of the whole-image pass.
        val modelFile = DeviceFixtures.requireModel(ModelId.YOLOE_DETECT)
        val bitmap = Bitmap.createBitmap(1920, 1080, Bitmap.Config.ARGB_8888).apply {
            val canvas = Canvas(this)
            canvas.drawColor(Color.rgb(114, 114, 114))
        }
        YoloDetector(modelFile.absolutePath).use { detector ->
            val start = SystemClock.elapsedRealtime()
            detector.detect(bitmap)
            val elapsed = SystemClock.elapsedRealtime() - start
            // Budget is the emulator's, not the product's: the x86-on-arm64
            // translation runs ONNX far slower than a real arm64 device (this
            // 1920px multiscale path measures 15-23s here vs ~4-6s on hardware).
            // The 15s UX deadline is a product contract the real-device gates
            // enforce; this gate only proves the path completes without hanging.
            assertTrue(elapsed < 30_000, "multiscale detect took ${elapsed}ms (emulator budget 30s)")
        }
    }
}
