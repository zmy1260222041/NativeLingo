package com.nativelingo.scoring

import com.nativelingo.scoring.detail.WordSpan
import com.nativelingo.scoring.detail.computeWordDetails
import com.nativelingo.scoring.io.NpyReader
import com.nativelingo.scoring.io.frames2dInt
import com.nativelingo.scoring.io.toFloatArray1d
import com.nativelingo.scoring.score.CalibrationLoader
import kotlin.test.Test
import kotlin.test.assertEquals

/**
 * FR-6 parity: reproject the macOS DTW path onto the reference word grid in
 * Kotlin and assert every word's status (good/weak/bad/missed) matches the
 * macOS `compute_word_details` golden. Status is categorical, so this is an
 * exact-match check.
 */
class DetailParityTest {

    private val calib by lazy { CalibrationLoader.loadDefault() }
    private val pairs = listOf("samevoice", "speakervariance", "wrongtext", "slow")

    private fun golden(path: String) =
        javaClass.getResourceAsStream("/golden/$path")
            ?: error("missing golden resource: /golden/$path")

    @Test
    fun word_statuses_match_macos() {
        for (name in pairs) {
            val path = NpyReader.read(golden("pair/${name}_path.npy")).frames2dInt()
            val costs = NpyReader.read(golden("pair/${name}_costs.npy")).toFloatArray1d()
            val detail = golden("pair/${name}_detail.json").bufferedReader().use { it.readText() }

            val words = Regex(
                """"word":\s*"([^"]*)"[^}]*?"start":\s*([0-9.]+)[^}]*?"end":\s*([0-9.]+)"""
            ).findAll(detail).map {
                WordSpan(it.groupValues[1], it.groupValues[2].toFloat(), it.groupValues[3].toFloat())
            }.toList()
            val goldenStatus = Regex(""""status":\s*"([^"]*)"""").findAll(detail)
                .map { it.groupValues[1] }.toList()

            assertEquals(goldenStatus.size, words.size, "word/status count mismatch on $name")
            val result = computeWordDetails(path, costs, words, calib)
            assertEquals(goldenStatus.size, result.size, "result size mismatch on $name")
            for (i in result.indices) {
                assertEquals(goldenStatus[i], result[i].status,
                    "status mismatch on '$name' word '${result[i].word}': expected ${goldenStatus[i]}, got ${result[i].status}")
            }
        }
    }
}
