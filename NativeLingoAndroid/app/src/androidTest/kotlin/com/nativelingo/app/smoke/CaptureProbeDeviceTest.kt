package com.nativelingo.app.smoke

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.math.abs

private const val TAG_SMOKE = "NLSmoke"

/**
 * Diagnostic, not a gate: find which (sample rate, AudioSource) the emulator's
 * microphone actually delivers data on. The learner recorder switched 16 kHz
 * (buzzing) -> 44.1 kHz (silent), so rather than keep guessing rates, this
 * records half a second at several combinations and logs the init state, the
 * frame count [AudioRecord.read] returned, and the max sample amplitude.
 *
 * Run: gradlew :app:connectedDebugAndroidTest -Pandroid.testInstrumentationRunnerArguments.class=com.nativelingo.app.smoke.CaptureProbeDeviceTest
 */
@RunWith(AndroidJUnit4::class)
class CaptureProbeDeviceTest {

    private val combos = listOf(
        16_000 to "UNPROCESSED",
        44_100 to "UNPROCESSED",
        48_000 to "UNPROCESSED",
        16_000 to "MIC",
        44_100 to "MIC",
        48_000 to "MIC",
    )

    @Test
    fun probe_capture_combos() {
        val src = { name: String -> if (name == "UNPROCESSED") MediaRecorder.AudioSource.UNPROCESSED else MediaRecorder.AudioSource.MIC }
        for ((rate, source) in combos) {
            val minBuf = AudioRecord.getMinBufferSize(rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
            val ar = AudioRecord(src(source), rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, maxOf(minBuf * 2, rate * 2))
            val state = when (ar.state) {
                AudioRecord.STATE_INITIALIZED -> "INIT"
                else -> "UNINIT"
            }
            var framesRead = 0
            var maxAbs = 0
            if (ar.state == AudioRecord.STATE_INITIALIZED) {
                ar.startRecording()
                val halfSec = ShortArray(rate / 2)
                val n = ar.read(halfSec, 0, halfSec.size)
                framesRead = if (n > 0) n else n // negative == ERROR code
                if (n > 0) maxAbs = (0 until n).maxOf { abs(halfSec[it].toInt()) }
                ar.stop()
            }
            ar.release()
            Log.i(TAG_SMOKE, "rate=%-6d src=%-11s minBuf=%-7d %s read=%-8d maxAbs=%d".format(rate, source, minBuf, state, framesRead, maxAbs))
        }
    }
}
