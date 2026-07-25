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

/**
 * 2-D `.npy` payload as a Double frame matrix — for CTC Viterbi (Gate B/C),
 * which accumulates in float64 to match `phoneme._viterbi_align`.
 */
fun NpyArray.frames2dDouble(): Array<DoubleArray> {
    require(rank() == 2) { "expected a 2-D array, got shape ${shape.toList()}" }
    val rows = shape[0]
    val cols = shape[1]
    val out = Array(rows) { DoubleArray(cols) }
    var idx = 0
    for (r in 0 until rows) {
        val row = out[r]
        for (c in 0 until cols) row[c] = data[idx++]
    }
    return out
}

/** 2-D `.npy` payload as an Int matrix — e.g. a DTW alignment path (K, 2). */
fun NpyArray.frames2dInt(): Array<IntArray> {
    require(rank() == 2) { "expected a 2-D array, got shape ${shape.toList()}" }
    val rows = shape[0]
    val cols = shape[1]
    val out = Array(rows) { IntArray(cols) }
    var idx = 0
    for (r in 0 until rows) {
        val row = out[r]
        for (c in 0 until cols) row[c] = data[idx++].toInt()
    }
    return out
}

/** 1-D `.npy` payload as a FloatArray — e.g. DTW per-step costs. */
fun NpyArray.toFloatArray1d(): FloatArray {
    require(rank() == 1) { "expected a 1-D array, got shape ${shape.toList()}" }
    return FloatArray(size) { data[it].toFloat() }
}
