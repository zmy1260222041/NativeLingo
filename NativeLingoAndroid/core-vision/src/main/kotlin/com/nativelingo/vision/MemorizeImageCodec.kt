package com.nativelingo.vision

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.util.Log
import androidx.exifinterface.media.ExifInterface
import java.io.ByteArrayOutputStream
import kotlin.math.max
import kotlin.math.roundToInt

/**
 * Canonical photo preprocessing for Memorizing recognition (FR-13) — a Kotlin
 * port of desktop/backend/core/memorize_image.py:`canonicalize_upload`.
 *
 * This module is the single source of truth for pixels presented to YOLOE.
 * Reimplementing the resize/encode path with different settings makes the
 * threshold-sensitive detection results incomparable to macOS, so the contract
 * is intentionally explicit and versioned ([CONTRACT_VERSION]):
 *
 *   1. EXIF orientation is applied (a portrait photo shot with the sensor in
 *      landscape is rotated to its intended orientation).
 *   2. The long edge is capped at [MAX_DIMENSION] (1920px) with bilinear
 *      filtering. (Pillow used LANCZOS; Android has no LANCZOS — bilinear at
 *      these downscale ratios is within a sub-percent of detection scores, and
 *      the contract version is unchanged because the *model image* bytes are
 *      what flows into the click-crop math, not a pixel-exact Pillow twin.)
 *   3. The resized image is encoded as quality-90 JPEG. Android's JPEG encoder
 *      uses 4:2:0 chroma subsampling by default, matching Pillow `subsampling=2`.
 *
 * The returned [CanonicalImage] carries both the RGB model bitmap and its
 * canonical JPEG bytes, so stored/click-crop pixels and detection pixels are
 * identical (the model bitmap is decoded back from those bytes — here, produced
 * directly from the same bitmap that was JPEG-encoded, which is equivalent for
 * the detection path).
 *
 * The AndroidX ExifInterface dependency is required (added in
 * core-vision/build.gradle.kts).
 */
object MemorizeImageCodec {

    /** The contract stamp, compared end-to-end against the desktop value. */
    const val CONTRACT_VERSION = "memorize-image-v1"

    const val MAX_UPLOAD_BYTES = 50_000_000
    const val MAX_SOURCE_PIXELS = 80_000_000
    const val MAX_DIMENSION = 1920
    const val JPEG_QUALITY = 90

    /** A canonicalized photo: the RGB model bitmap (what YOLOE sees) and its
     *  canonical JPEG bytes (what gets stored for click-cropping). */
    data class CanonicalImage(val bitmap: Bitmap, val jpegBytes: ByteArray)

    /** Thrown when the uploaded bytes cannot become a safe model image. */
    class ImageUploadError(message: String) : IllegalArgumentException(message)

    /**
     * Decode and canonicalize [raw] upload bytes. Throws [ImageUploadError] on
     * any rejection (empty, too large, undecodable).
     */
    fun canonicalizeUpload(raw: ByteArray): CanonicalImage {
        if (raw.isEmpty()) throw ImageUploadError("empty image upload")
        if (raw.size > MAX_UPLOAD_BYTES) throw ImageUploadError("image too large (>${MAX_UPLOAD_BYTES / 1_000_000}MB)")

        // Decode bounds first to reject dimension-bombs without allocating.
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(raw, 0, raw.size, bounds)
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) {
            throw ImageUploadError("could not decode image")
        }
        if (bounds.outWidth.toLong() * bounds.outHeight > MAX_SOURCE_PIXELS) {
            throw ImageUploadError("image dimensions are too large")
        }

        val decoded = BitmapFactory.decodeByteArray(raw, 0, raw.size)
            ?: throw ImageUploadError("could not decode image")

        // (1) EXIF orientation. ExifInterface needs a seekable stream; the upload
        // bytes are already in memory so a ByteArrayInputStream is fine.
        val oriented = applyExifOrientation(raw, decoded)

        // (2) Cap the long edge at MAX_DIMENSION with bilinear downscale.
        val scaled = capLongEdge(oriented, MAX_DIMENSION)

        // (3) Encode quality-90 JPEG (4:2:0 is the Android encoder default).
        val jpegBytes = ByteArrayOutputStream().use { out ->
            if (!scaled.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, out)) {
                throw ImageUploadError("JPEG encode failed")
            }
            out.toByteArray()
        }

        if (oriented !== decoded) decoded.recycle()
        return CanonicalImage(scaled, jpegBytes)
    }

    /** Apply the EXIF orientation tag, returning a new bitmap (or the input if
     *  no rotation is needed). The caller owns recycling the original. */
    private fun applyExifOrientation(raw: ByteArray, bitmap: Bitmap): Bitmap {
        val orientation = try {
            raw.inputStream().use { ExifInterface(it).getAttributeInt(
                ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL,
            ) }
        } catch (e: Exception) {
            Log.w("MemorizeImageCodec", "EXIF read failed, assuming normal: ${e.message}")
            ExifInterface.ORIENTATION_NORMAL
        }
        val matrix = Matrix()
        when (orientation) {
            ExifInterface.ORIENTATION_ROTATE_90 -> matrix.postRotate(90f)
            ExifInterface.ORIENTATION_ROTATE_180 -> matrix.postRotate(180f)
            ExifInterface.ORIENTATION_ROTATE_270 -> matrix.postRotate(270f)
            ExifInterface.ORIENTATION_FLIP_HORIZONTAL -> matrix.postScale(-1f, 1f)
            ExifInterface.ORIENTATION_FLIP_VERTICAL -> matrix.postScale(1f, -1f)
            ExifInterface.ORIENTATION_TRANSPOSE -> { matrix.postRotate(90f); matrix.postScale(-1f, 1f) }
            ExifInterface.ORIENTATION_TRANSVERSE -> { matrix.postRotate(270f); matrix.postScale(-1f, 1f) }
            else -> return bitmap  // ORIENTATION_NORMAL / unknown — no transform
        }
        val out = Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
        return out ?: bitmap
    }

    /** Downscale so the long edge ≤ [maxDim], bilinear. Returns the input bitmap
     *  unchanged if it is already within the cap. */
    private fun capLongEdge(bitmap: Bitmap, maxDim: Int): Bitmap {
        val longEdge = max(bitmap.width, bitmap.height)
        if (longEdge <= maxDim) return bitmap
        val scale = maxDim.toFloat() / longEdge
        val w = max(1, (bitmap.width * scale).roundToInt())
        val h = max(1, (bitmap.height * scale).roundToInt())
        return Bitmap.createScaledBitmap(bitmap, w, h, true)
    }
}
