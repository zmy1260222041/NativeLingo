package com.nativelingo.vision

import org.json.JSONObject

/**
 * The curated label → {zh, min_score} table for FR-13 macro detection — a Kotlin
 * port of desktop/backend/core/vision.py:`_load_label_specs`.
 *
 * Prompt-free YOLOE exposes thousands of labels (actions, scene types, noisy
 * aliases), most of which are harmful in a language-learning UI. The five JSON
 * files shipped under `resources/com/nativelingo/vision/labels/` are, together:
 *
 *  1. a tangible-object allowlist (only these labels can ever reach the UI); and
 *  2. a per-label confidence calibration table.
 *
 * Merge order MUST match the desktop port exactly, or the same photo diverges:
 *
 *  1. COCO (`coco_names.txt` ∥ `coco_zh.json`) minus `person`, at the
 *     `_default_coco_min_score` floor (0.6). A label not in the ONNX embedded
 *     vocabulary is dropped — the model can never emit it.
 *  2. `yoloe_everyday_labels.json` categories raise each label's `min_score` to
 *     `max(current, category_floor)`.
 *  3. `yoloe_labels.json["labels"]` is the final override — it sets both `zh`
 *     and `min_score` definitively.
 *  4. Any label absent from the model vocabulary is dropped.
 *
 * `parts_zh.json` is NOT consumed here — it belongs to FR-14 (parts), staged for
 * a later phase. It ships alongside so the module is self-contained.
 */
data class LabelSpec(
    val zh: String,
    val minScore: Float,
)

object LabelSpecs {

    /**
     * Build the curated table for the given ONNX-embedded class vocabulary.
     *
     * @param modelNames the YOLOE ONNX `names` metadata: class id → English label.
     *   Only labels present here can survive — this is the gate that drops labels
     *   the shipped model cannot emit.
     */
    fun load(modelNames: Map<Int, String>): Map<String, LabelSpec> {
        val available: Set<String> = modelNames.values.toSet()

        val cocoEn = readResource("labels/coco_names.txt").lineSequence()
            .map { it.trim() }.filter { it.isNotEmpty() }.toList()
        val cocoZh = readResource("labels/coco_zh.json").let(::jsonStringArray)
        require(cocoEn.size == cocoZh.size) {
            "coco_names.txt (${cocoEn.size}) and coco_zh.json (${cocoZh.size}) disagree"
        }

        val labelsJson = JSONObject(readResource("labels/yoloe_labels.json"))
        val everydayJson = JSONObject(readResource("labels/yoloe_everyday_labels.json"))

        val defaultScore = labelsJson.getDouble("_default_coco_min_score").toFloat()

        // (1) COCO baseline — drop `person` and anything outside the model vocab.
        val specs = LinkedHashMap<String, LabelSpec>()
        for ((labelEn, labelZh) in cocoEn.zip(cocoZh)) {
            if (labelEn == "person" || labelEn !in available) continue
            specs[labelEn] = LabelSpec(labelZh, defaultScore)
        }

        // (2) everyday categories raise the floor per category.
        val categoryFloors = everydayJson.getJSONObject("_category_min_score_floors")
        val categories = everydayJson.getJSONObject("categories")
        for (categoryName in categories.keys()) {
            val floor = categoryFloors.getDouble(categoryName).toFloat()
            val category = categories.getJSONObject(categoryName)
            for (label in category.keys()) {
                val spec = category.getJSONObject(label)
                val raised = maxOf(spec.getDouble("min_score").toFloat(), floor)
                if (label !in available) continue
                specs[label] = LabelSpec(spec.getString("zh"), raised)
            }
        }

        // (3) yoloe_labels.json is the final override (zh + min_score).
        val overrides = labelsJson.getJSONObject("labels")
        for (label in overrides.keys()) {
            if (label !in available) continue
            val spec = overrides.getJSONObject(label)
            specs[label] = LabelSpec(spec.getString("zh"), spec.getDouble("min_score").toFloat())
        }

        return specs
    }

    // ── resource plumbing ─────────────────────────────────────────────────────

    /** Read a classpath resource as UTF-8 text. Throws if absent — a missing label
     *  file is a build-time packaging bug, not a runtime condition to swallow. */
    private fun readResource(path: String): String {
        val stream = LabelSpecs::class.java.getResourceAsStream("/com/nativelingo/vision/$path")
            ?: error("label resource missing on classpath: $path")
        return stream.bufferedReader().use { it.readText() }
    }

    /** Parse a top-level JSON array of strings (coco_zh.json is exactly this). */
    private fun jsonStringArray(text: String): List<String> =
        org.json.JSONArray(text).let { arr -> List(arr.length()) { arr.getString(it) } }
}
