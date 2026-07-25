package com.nativelingo.scoring.score

import kotlin.math.abs
import kotlin.math.ln
import kotlin.math.max

data class GamComponent(
    val feature: String,
    val weight: Float,
    val x: FloatArray,
    val y: FloatArray,
)

/**
 * Calibrated score mapping shipped verbatim from macOS (`backend/core/calibration.json`):
 *  - accuracy: isotonic regression on the mean DTW cosine cost
 *  - fluency: a monotone GAM over [path_dev, |log rate|, pause_ratio]
 *
 * Fitted on speechocean762. Ported as-is, NOT refit — NFR-Q1 says the calibration
 * must match macOS; Android's job is to reproduce the *inputs* (cost / features),
 * not the mapping. The mapping itself is data.
 */
data class Calibration(
    val accuracyX: FloatArray,
    val accuracyY: FloatArray,
    val components: List<GamComponent>,
) {
    /** Port of score_b.accuracy_from_cost. */
    fun accuracyFromCost(cost: Float): Float =
        npInterp(cost, accuracyX, accuracyY).coerceIn(0f, 100f)

    /** Port of score_b.fluency_from_features. ``pausePerS`` is accepted but the
     *  GAM doesn't use it (kept for signature parity). */
    fun fluencyFromFeatures(
        pathDev: Float, rateRatio: Float, pausePerS: Float, pauseRatio: Float,
    ): Float {
        val values = mapOf(
            "path_dev" to pathDev,
            "lograte" to abs(ln(max(rateRatio, 1e-3f))),
            "pause_ratio" to pauseRatio,
        )
        var score = 0f
        for (c in components) {
            val v = values[c.feature] ?: continue
            score += c.weight * npInterp(v, c.x, c.y).coerceIn(0f, 100f)
        }
        return score.coerceIn(0f, 100f)
    }
}

/** numpy.interp: linear interpolation, clamped to endpoints (xp increasing). */
private fun npInterp(x: Float, xp: FloatArray, fp: FloatArray): Float {
    if (xp.isEmpty()) return Float.NaN
    val last = xp.size - 1
    if (x <= xp[0]) return fp[0]
    if (x >= xp[last]) return fp[last]
    var i = 1
    while (i < last && xp[i] < x) i++
    val x0 = xp[i - 1]; val x1 = xp[i]
    val f0 = fp[i - 1]; val f1 = fp[i]
    return f0 + (f1 - f0) * (x - x0) / (x1 - x0)
}

/**
 * Loads calibration.json. Uses targeted regex rather than a JSON dependency —
 * the schema is fixed and trusted (our own shipped file), and this keeps
 * :core-scoring stdlib-only. On Android you may equally use org.json.
 */
object CalibrationLoader {
    fun loadDefault(): Calibration {
        val res = CalibrationLoader::class.java.getResourceAsStream("/calibration.json")
            ?: error("calibration.json not on classpath")
        return load(res.bufferedReader().use { it.readText() })
    }

    fun load(text: String): Calibration {
        val accBlock = text.substringAfter("\"accuracy_isotonic\"").substringBefore("\"fluency_gam\"")
        val comps = Regex("""\{[^{}]*"feature"[^{}]*\}""").findAll(text).map { m ->
            val o = m.value
            GamComponent(
                feature = Regex(""""feature"\s*:\s*"([^"]*)"""").find(o)!!.groupValues[1],
                weight = Regex(""""weight"\s*:\s*([0-9.eE+-]+)""").find(o)!!.groupValues[1].toFloat(),
                x = floatArray(o, "x"),
                y = floatArray(o, "y"),
            )
        }.toList()
        return Calibration(floatArray(accBlock, "x"), floatArray(accBlock, "y"), comps)
    }

    private fun floatArray(block: String, key: String): FloatArray {
        val m = Regex(""""$key"\s*:\s*\[([^\]]*)\]""").find(block)
            ?: error("'$key' array not found in calibration.json block")
        return m.groupValues[1].split(',')
            .map { it.trim() }.filter { it.isNotEmpty() }.map { it.toFloat() }.toFloatArray()
    }
}
