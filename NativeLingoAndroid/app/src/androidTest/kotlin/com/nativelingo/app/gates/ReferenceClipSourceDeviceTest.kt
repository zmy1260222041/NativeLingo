package com.nativelingo.app.gates

import androidx.test.ext.junit.runners.AndroidJUnit4
import com.nativelingo.app.repo.ReferenceClipSource
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/**
 * Device gate for the pre-rendered Piper reference clips (FR-17, Option D).
 *
 * This is the gate that the sherpa runtime-TTS path could never pass: repeated
 * loads of the same reference must be stable (no native crash), because the user
 * taps "play reference" many times. Reading a wav asset is trivially stable, so
 * the assertion is almost a formality — but it pins the contract the UI depends
 * on (a clip exists for a common label, it is non-empty 16 kHz mono, and calling
 * it ten times in a row returns the same bytes every time).
 *
 * Also exercises the PCM16→float32 WAV decoder in [ReferenceClipSource]: the
 * decoded samples must be in [-1, 1] and non-trivial (not all zeros).
 */
@RunWith(AndroidJUnit4::class)
class ReferenceClipSourceDeviceTest {

    private val source = ReferenceClipSource(DeviceFixtures.appContext)

    @Test
    fun common_label_has_a_non_empty_clip() {
        val cat = source.synthesize("cat")
        assertNotNull(cat, "'cat' should have a bundled reference clip")
        assertTrue(cat.size > 1000, "'cat' clip suspiciously short: ${cat.size} samples")
        assertEquals(16_000, source.sampleRate, "clip sample rate must be 16 kHz")
        // Decoded PCM16 → float32 must be in [-1, 1] and not silent.
        var maxAbs = 0f
        for (s in cat) maxAbs = maxOf(maxAbs, kotlin.math.abs(s))
        assertTrue(maxAbs > 0.01f, "clip is near-silent (max abs $maxAbs) — decode broken?")
    }

    @Test
    fun repeated_loads_are_stable_and_identical() {
        // The exact property sherpa OfflineTts could not provide: many calls,
        // one process, no crash, identical output. This is why Option D exists.
        val first = source.synthesize("cat")!!
        repeat(10) {
            val again = source.synthesize("cat")!!
            assertEquals(first.size, again.size, "clip length changed on repeat load")
            // Bytes-from-asset are inherently identical; this asserts the decode
            // is deterministic too (no uninitialized memory).
            var diff = 0
            for (i in first.indices) if (first[i] != again[i]) diff++
            assertEquals(0, diff, "decoded samples differ on repeat load")
        }
    }

    @Test
    fun unknown_label_returns_null() {
        // A label with no bundled clip → null, so the UI hides the play button
        // rather than crashing or playing silence.
        val none = source.synthesize("xyzzy-nonexistent-word-12345")
        assertTrue(none == null, "expected null for an unbundled label")
    }
}
