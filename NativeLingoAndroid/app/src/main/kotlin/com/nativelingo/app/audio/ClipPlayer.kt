package com.nativelingo.app.audio

import android.content.Context
import androidx.media3.common.MediaItem
import androidx.media3.exoplayer.ExoPlayer
import com.nativelingo.scoring.io.WavIo
import java.io.File
import kotlin.math.max
import kotlin.math.min

/**
 * FR-8 A/B replay for short audio clips — reference and learner alike. macOS
 * cuts exact WAV slices server-side because `<audio>` currentTime seek gives only
 * ~250 ms granularity and truncates tails; here the slice is cut sample-accurately
 * in-process ([WavIo.writePcm16]) and played by a single ExoPlayer that owns no
 * surface (the muted-video player for FR-3 is a separate ExoPlayer in the studio
 * screen, since it needs a PlayerView).
 *
 * One player, stop-before-play: starting a clip stops any in-flight one, matching
 * macOS `stopAllClips`.
 */
class ClipPlayer(context: Context) {

    private val cacheDir: File = context.cacheDir
    private val exo: ExoPlayer = ExoPlayer.Builder(context).build()

    /** Play `[startS, endS]` of `samples` as a fresh WAV clip. No-op on an empty span. */
    fun playClip(samples: FloatArray, startS: Float, endS: Float, sampleRate: Int = 16000) {
        if (endS <= startS) return
        val a = max(0, (startS * sampleRate).toInt())
        val b = min(samples.size, (endS * sampleRate).toInt())
        if (b <= a) return
        val clip = File.createTempFile("clip", ".wav", cacheDir)
        clip.outputStream().use { it.write(WavIo.writePcm16(samples.copyOfRange(a, b), sampleRate)) }
        clip.deleteOnExit()
        exo.stop()
        exo.setMediaItem(MediaItem.fromUri(clip.absolutePath))
        exo.prepare()
        exo.playWhenReady = true
    }

    fun stop() {
        exo.stop()
    }

    fun release() {
        exo.release()
    }
}
