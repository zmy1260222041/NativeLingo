package com.nativelingo.app.memorize

import android.graphics.Bitmap
import com.nativelingo.vision.YoloDetector
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap

/**
 * The in-process single source of truth for an analyzed photo — the Android
 * equivalent of desktop/backend/main.py `_MEMORIZE_META`.
 *
 * The contract from the desktop port is preserved verbatim: the UI never owns
 * the object boxes. It hands back an [objectId] and the pipeline re-derives the
 * object server-side (here, inside the process). This is why [analyze] is the
 * only entry point that accepts pixels, and why [objectFor] is the only way a
 * later stage (click-crop, parts, scenario) may read a box. A caller that
 * supplied its own `box` would be a bug, not a shortcut.
 *
 * Entries live until [clear] (the user uploads a new photo) — there is at most
 * one photo in flight in the stage machine, mirroring the desktop tab.
 */
class MemorizeStore {

    /** An analyzed photo: its canonical bitmap, the detection list, and the
     *  preprocessing contract stamp that produced these pixels. */
    data class Photo(
        val id: String,
        val bitmap: Bitmap,
        val objects: List<YoloDetector.Detection>,
        val preprocessing: String,
    )

    private val photos = ConcurrentHashMap<String, Photo>()

    /** Store a fresh analysis under a new random id; returns that id. */
    fun put(bitmap: Bitmap, objects: List<YoloDetector.Detection>, preprocessing: String): String {
        val id = UUID.randomUUID().toString().replace("-", "")
        photos[id] = Photo(id, bitmap, objects, preprocessing)
        return id
    }

    /** Re-derive the object for [photoId]/[objectId] — the only sanctioned way a
     *  later stage reads a box. Null if the photo/object is gone (new upload). */
    fun objectFor(photoId: String, objectId: Int): YoloDetector.Detection? =
        photos[photoId]?.objects?.firstOrNull { it.id == objectId }

    fun photo(photoId: String): Photo? = photos[photoId]

    /** Drop everything — the UI calls this when the user picks a new photo, so a
     *  stale click on the old image can never reach the new one's boxes. */
    fun clear() = photos.clear()
}
