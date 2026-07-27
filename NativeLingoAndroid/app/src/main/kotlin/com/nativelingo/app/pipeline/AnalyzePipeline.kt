package com.nativelingo.app.pipeline

import com.nativelingo.align.AlignedSpan
import com.nativelingo.align.ForcedAligner
import com.nativelingo.app.model.AnalysisResult
import com.nativelingo.app.model.AnalyzedSentence
import com.nativelingo.app.model.AnalyzedWord
import com.nativelingo.audio.DecodedAudio
import com.nativelingo.embed.Wav2Vec2Encoder
import com.nativelingo.scoring.align.dtwAlign
import com.nativelingo.scoring.audio.AudioPreproc
import com.nativelingo.scoring.audio.PauseFeatures
import com.nativelingo.scoring.detail.SentenceSpan
import com.nativelingo.scoring.detail.WordSpan
import com.nativelingo.scoring.detail.computeSentenceDetails
import com.nativelingo.scoring.feedback.generateFeedback
import com.nativelingo.scoring.norm.normalizePair
import com.nativelingo.scoring.score.Calibration
import com.nativelingo.scoring.score.scoreTrackB
import com.nativelingo.scoring.worddiff.LearnerWord
import com.nativelingo.scoring.worddiff.NoPitch
import com.nativelingo.scoring.worddiff.RefWord
import com.nativelingo.scoring.worddiff.diagnoseWords
import kotlin.math.max
import kotlin.math.min

/**
 * In-process port of `backend/core/pipeline.py:analyze_detailed` — the
 * "reference clip + learner take + sentence grid -> scores + per-word detail"
 * orchestration. Replaces the macOS loopback HTTP `/analyze_video` with direct
 * Kotlin calls into the cores.
 *
 * FR-11 (phoneme MDD, macOS pipeline.py:205-229) is deliberately omitted this
 * round (PRD v0.4): `:core-mdd` is post-v1.0. The prosody summary (Track A
 * intonation/pause match) is also omitted — it needs F0 tracking (TarsosDSP),
 * the same gap as FR-7 pitch; `generateFeedback(trackB, prosody = null)` is the
 * no-prosody path macOS already has.
 *
 * Heavy collaborators (encoder, aligner) are owned by [com.nativelingo.app.di.AppContainer]
 * and live for the process — one wav2vec2 session and one MMS session no matter
 * how many analyses run, which is what Gate D's peak-RSS budget assumes.
 */
class AnalyzePipeline(
    private val encoder: Wav2Vec2Encoder,
    private val aligner: ForcedAligner,
    private val calibration: Calibration,
) {

    fun analyzeDetailed(
        ref: DecodedAudio,
        learnerSamples: FloatArray,
        videoSentences: List<SentenceSpan>,
    ): AnalysisResult {
        val refSamples = ref.samples
        // The decoded reference's sample-0 sits at `ref.startS` (<= the requested
        // segStart — MediaCodec consumes the first post-seek frame as priming, see
        // PRE_ROLL_S). `videoSentences` times are on the video timeline;
        // computeSentenceDetails maps times->frames against the reference embeddings,
        // whose frame 0 is refSamples[0] <-> startS. So projection needs startS-
        // relative times. The frame shift and the sample shift cancel against
        // macOS's own seek-and-keep, so the same audio maps either way; this keeps
        // the Android side self-consistent rather than offset by the pre-roll.
        val offset = ref.startS.toFloat()
        val clipSentences = videoSentences.map { s ->
            SentenceSpan(
                text = s.text,
                start = s.start - offset,
                end = s.end - offset,
                words = s.words.map { w -> WordSpan(w.word, w.start - offset, w.end - offset) },
            )
        }
        val wordStrings = videoSentences.flatMap { it.words.map { it.word } }

        // Keep the untrimmed learner: its timeline is what FR-8 replays and what
        // forced alignment runs against. Trim only for scoring; carry the offset so
        // learner spans map back onto the original recording.
        val learnerTrim = AudioPreproc.trimSilenceWithOffset(learnerSamples)
        val learnerTrimmed = learnerTrim.wav
        val learnerOffset = learnerTrim.offsetS.toFloat()

        val refEmb = encoder.encode(refSamples)
        val learnerEmb = encoder.encode(learnerTrimmed)
        val (refN, learnerN) = normalizePair(refEmb, learnerEmb)
        val dtw = dtwAlign(refN, learnerN)

        val (pausePerS, pauseRatio) = PauseFeatures.fluencyInputs(learnerTrimmed)
        val trackB = scoreTrackB(
            dtw.path, dtw.pathCosts, dtw.normalizedCost,
            refLen = refEmb.size, learnerLen = learnerEmb.size,
            pausePerS = pausePerS.toFloat(), pauseRatio = pauseRatio.toFloat(),
            calibration = calibration,
        )
        val feedback = generateFeedback(trackB, prosody = null)

        val details = computeSentenceDetails(
            dtw.path, dtw.pathCosts, clipSentences, calibration, learnerOffset,
        )

        // Flat reference word list (with statuses) and the parallel learner-span
        // slot, both indexed by a running flat counter. wordStrings is the same
        // words in the same order, for forced alignment.
        val refFlat = ArrayList<RefWord>()
        val wordLearnerSpan = ArrayList<FloatArray?>() // [start, end] or null
        val learnerFlat = ArrayList<LearnerWord>()
        for ((si, d) in details.withIndex()) {
            for ((wi, w) in d.words.withIndex()) {
                refFlat.add(RefWord(si, wi, w.word, w.start, w.end, w.status))
                wordLearnerSpan.add(null)
                learnerFlat.add(LearnerWord(w.word, 0f, 0f))
            }
        }

        val learnerDurSec = learnerSamples.size / 16000.0f

        // Learner replay spans: align the REFERENCE transcript to the learner's
        // audio (not an ASR decode of what was said) so every word maps 1:1,
        // mispronunciations included — macOS pipeline.py:143-170. Pads each word
        // -0.03/+0.06 s so the clip isn't shaved at the edges.
        val aligned = runCatching { aligner.align(wordStrings, learnerSamples) }.getOrNull()
        val sentLearnerStart = HashMap<Int, Float>()
        val sentLearnerEnd = HashMap<Int, Float>()
        if (aligned != null) {
            val sentStarts = HashMap<Int, MutableList<Float>>()
            val sentEnds = HashMap<Int, MutableList<Float>>()
            for (idx in refFlat.indices) {
                val sp: AlignedSpan? = aligned.getOrNull(idx)
                if (sp != null) {
                    val s = max(0.0f, sp.startS - 0.03f)
                    val e = min(learnerDurSec, sp.endS + 0.06f)
                    wordLearnerSpan[idx] = floatArrayOf(s, e)
                    learnerFlat[idx] = LearnerWord(refFlat[idx].word, s, e)
                    val si = refFlat[idx].si
                    (sentStarts[si] ?: mutableListOf<Float>().also { sentStarts[si] = it }).add(s)
                    (sentEnds[si] ?: mutableListOf<Float>().also { sentEnds[si] = it }).add(e)
                }
            }
            for (si in sentStarts.keys) {
                val starts = sentStarts[si]
                val ends = sentEnds[si]
                if (starts != null && ends != null) {
                    sentLearnerStart[si] = max(0.0f, starts.min() - 0.05f)
                    sentLearnerEnd[si] = min(learnerDurSec, ends.max() + 0.10f)
                }
            }
        }
        // M1: no difflib fallback when alignment fails (macOS pipeline.py:171-185
        // would transcribe the learner). On a clean take alignment succeeds; a
        // failure leaves learner spans at 0, which the UI shows as "no replay for
        // this word" — acceptable degradation, and the bundled path doesn't load
        // Whisper to run the fallback anyway.

        // Per-word pronunciation improvement directions (FR-7). Pitch tips are
        // excluded (NoPitch) — same equivalence gap macOS's `_tips_nopitch`
        // golden captures; TarsosDSP wiring is a device-side follow-up.
        val diffs = runCatching {
            diagnoseWords(refSamples, learnerSamples, refFlat, learnerFlat, NoPitch)
        }.getOrDefault(emptyMap())

        // Assemble. `diffs` is keyed (sentenceIndex, withinSentenceWordIndex), so
        // mapIndexed's `wi` addresses it directly; the flat counter walks the
        // flat-indexed learner-span slot in lockstep.
        var flatIdx = 0
        val analyzedSentences = details.map { d ->
            val words = d.words.mapIndexed { wi, w ->
                val span = wordLearnerSpan[flatIdx]
                val tip = diffs[Pair(d.index, wi)]?.tip ?: ""
                flatIdx++
                AnalyzedWord(
                    word = w.word,
                    start = w.start,
                    end = w.end,
                    accuracy = w.accuracy,
                    status = w.status,
                    tip = tip,
                    learnerStart = span?.get(0) ?: 0f,
                    learnerEnd = span?.get(1) ?: 0f,
                )
            }
            AnalyzedSentence(
                index = d.index,
                text = d.text,
                start = d.start,
                end = d.end,
                accuracy = d.accuracy,
                fluency = d.fluency,
                learnerStart = sentLearnerStart[d.index] ?: 0f,
                learnerEnd = sentLearnerEnd[d.index] ?: 0f,
                words = words,
            )
        }

        return AnalysisResult(
            overallScore = feedback.overallScore,
            overallBand = feedback.overallBand,
            accuracy = feedback.accuracy,
            fluency = feedback.fluency,
            speechRateRatio = feedback.speechRateRatio,
            tips = feedback.tips,
            sentences = analyzedSentences,
            refSamples = refSamples,
            learnerSamples = learnerSamples,
        )
    }
}
