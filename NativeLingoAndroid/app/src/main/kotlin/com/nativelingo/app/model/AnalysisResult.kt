package com.nativelingo.app.model

/**
 * UI-facing analysis result — what `AnalyzePipeline` returns and the results
 * screen renders.
 *
 * This is a **separate type from `:core-scoring`'s `WordDetail`/`SentenceDetail`**
 * on purpose. The core types are the *pre-enrichment* shape (their file header
 * states `tip` / learner spans are "filled in downstream by word_diff + forced
 * alignment"), and the JVM parity tests assert exactly that shape. Widening them
 * would either break those tests or drag enrichment into the pure-JVM module.
 * macOS sidesteps this by mutating a Python dict post-hoc; Kotlin gets a typed
 * result assembled at the seam where the enrichment happens — [AnalyzePipeline].
 *
 * Times on [AnalyzedWord]/[AnalyzedSentence]:
 *  - `start`/`end` are relative to the decoded reference clip's sample-0 (i.e.
 *    to `DecodedAudio.startS`), so they index straight into [AnalysisResult.refSamples].
 *  - `learnerStart`/`learnerEnd` index into [AnalysisResult.learnerSamples] (the
 *    untrimmed recording the UI replays), already shifted by the trim offset.
 */
data class AnalyzedWord(
    val word: String,
    val start: Float,
    val end: Float,
    val accuracy: Float,
    val status: String, // good | weak | bad | missed
    val tip: String,
    val learnerStart: Float,
    val learnerEnd: Float,
)

data class AnalyzedSentence(
    val index: Int,
    val text: String,
    val start: Float,
    val end: Float,
    val accuracy: Float,
    val fluency: Float,
    val learnerStart: Float,
    val learnerEnd: Float,
    val words: List<AnalyzedWord>,
)

data class AnalysisResult(
    val overallScore: Float,
    val overallBand: String,
    val accuracy: Float,
    val fluency: Float,
    val speechRateRatio: Float,
    val tips: List<String>,
    val sentences: List<AnalyzedSentence>,
    /** The decoded reference segment, sample-0 ↔ its `startS`. FR-8 slices this for reference clips. */
    val refSamples: FloatArray,
    /** The learner's raw (untrimmed) take. FR-8 slices this for "my" clips. */
    val learnerSamples: FloatArray,
) {
    // FloatArray identity equality is wrong by default; the result is logically a
    // value once the samples are captured. Compare by length + content.
    override fun equals(other: Any?): Boolean = this === other ||
        (other is AnalysisResult && overallScore == other.overallScore && sentences == other.sentences)
    override fun hashCode(): Int = overallScore.hashCode() * 31 + sentences.hashCode()
}
