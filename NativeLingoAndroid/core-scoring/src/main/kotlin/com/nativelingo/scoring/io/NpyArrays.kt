package com.nativelingo.scoring.io

/**
 * View a 2-D `.npy` payload as a frame matrix: row t holds the D-dim embedding
 * of frame t. Matches the (T, D) layout macOS dumps (wav2vec2 layers 6-9 mean,
 * MMS emission, …). Values are narrowed to Float — the macOS pipeline runs in
 * float32 downstream (align.py / speaker_norm.py), and the golden parity
 * tolerances (±0.02) absorb the narrowing.
 */
fun NpyArray.frames2d(): Array<FloatArray> {
    require(rank() == 2) { "expected a 2-D array, got shape ${shape.toList()}" }
    val rows = shape[0]
    val cols = shape[1]
    val out = Array(rows) { FloatArray(cols) }
    var idx = 0
    for (r in 0 until rows) {
        val row = out[r]
        for (c in 0 until cols) row[c] = data[idx++].toFloat()
    }
    return out
}
