package com.nativelingo.app.smoke

import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nativelingo.app.gates.DeviceFixtures
import com.nativelingo.app.memorize.MemorizePipeline
import com.nativelingo.models.ModelId
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import kotlin.test.assertTrue

/**
 * End-to-end smoke for the Memorizing pipeline (FR-13) on a real photo — the
 * on-device counterpart of the Speaking track's cloud smoke
 * (`CloudSpeakingDeviceTest`). 识物 never uploads; this is the one pipeline
 * that still runs fully locally (v0.7).
 *
 * Loads the canonicalized YOLOE model, runs a real photo of a cat through the
 * full `MemorizeImageCodec.canonicalizeUpload → YoloDetector.detect` path, and
 * asserts the curated vocabulary fires on a clear subject: the model must
 * return at least one detection, and "cat" must be among them (it is a COCO
 * label, well inside the model's training distribution). The pipeline also
 * exercises EXIF orientation, the 1920px cap, and the JPEG re-encode.
 *
 * The photo is staged at `cache/test_cat.jpg` by the test harness; if absent
 * the test fails hard (per the gate-suite convention — a self-skipping smoke
 * is worse than none).
 */
@RunWith(AndroidJUnit4::class)
class MemorizePipelineDeviceTest {

    @Test
    fun cat_photo_is_recognized_as_cat() {
        // The model must be staged for this gate to mean anything.
        val modelFile = DeviceFixtures.requireModel(ModelId.YOLOE_DETECT)

        // The cat photo ships inside the TEST APK's assets (app/src/androidTest/
        // assets/test_cat.jpg) so this gate is self-contained — no host-side
        // staging step to forget. Materialised to cacheDir because the pipeline
        // reads bytes.
        val photo = DeviceFixtures.assetToCache("test_cat.jpg")
        assertTrue(photo.isFile && photo.length() > 0,
            "test_cat.jpg not in test APK assets — app/src/androidTest/assets/")

        val pipeline = MemorizePipeline(
            com.nativelingo.vision.YoloDetector(modelFile.absolutePath),
        )
        val start = SystemClock.elapsedRealtime()
        val result = pipeline.analyze(photo.readBytes())
        val elapsed = SystemClock.elapsedRealtime() - start

        // Emulator budget, not the product's 15s UX deadline — the x86-on-arm64
        // translation runs ONNX far slower than real hardware (see
        // YoloDetectorDeviceTest). This gate proves the pipeline completes and
        // detects correctly; the UX deadline is a real-device gate concern.
        assertTrue(elapsed < 30_000, "analyze took ${elapsed}ms (emulator budget 30s)")
        assertTrue(result.objects.isNotEmpty(), "no objects detected on the cat photo")
        assertTrue(result.objects.any { it.labelEn == "cat" },
            "expected 'cat' in detections, got: ${result.objects.map { it.labelEn }}")
        assertTrue(result.preprocessing == "memorize-image-v1",
            "preprocessing contract stamp mismatch: ${result.preprocessing}")

        // The canonicalized long edge must be ≤ 1920 (the codec cap).
        val longEdge = maxOf(result.imageSize[0], result.imageSize[1])
        assertTrue(longEdge <= 1920, "canonicalized long edge $longEdge > 1920")
    }
}
