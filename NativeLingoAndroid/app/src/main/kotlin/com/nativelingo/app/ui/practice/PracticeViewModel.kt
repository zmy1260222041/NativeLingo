package com.nativelingo.app.ui.practice

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.nativelingo.app.di.AppContainer
import com.nativelingo.app.model.AnalysisResult
import com.nativelingo.app.repo.VideoRepository
import com.nativelingo.app.repo.WavEncoder
import com.nativelingo.audio.DecodedAudio
import com.nativelingo.scoring.detail.SentenceSpan
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Drives the whole practice flow for one video: sentence-range selection,
 * capture, analysis, and A/B replay. Scoped to the practice navigation entry so
 * it survives configuration changes; one VM owns the take and the result so the
 * results screen can slice both sample-accurately for FR-8.
 *
 * The muted-video ExoPlayer (FR-3) is NOT here — it needs a PlayerView surface,
 * so the studio screen owns it. Capture hardware ([com.nativelingo.app.audio.LearnerRecorder])
 * is here, because its output (the learner take) is flow state.
 */
class PracticeViewModel(
    private val container: AppContainer,
    val video: VideoRepository.CorpusVideo,
) : ViewModel() {

    /** Phase of the linear flow, derived from [UiState]. */
    enum class Phase { Loading, PickRange, Recording, ReadyToAnalyze, Results }

    data class UiState(
        val video: VideoRepository.CorpusVideo,
        val sentences: List<SentenceSpan> = emptyList(),
        val rangeStart: Int? = null,
        val rangeEnd: Int? = null,
        val studioEntered: Boolean = false,
        val isRecording: Boolean = false,
        val hasTake: Boolean = false,
        val isAnalyzing: Boolean = false,
        val result: AnalysisResult? = null,
        val error: String? = null,
    ) {
        val phase: Phase get() = when {
            result != null -> Phase.Results
            isRecording -> Phase.Recording
            studioEntered -> Phase.ReadyToAnalyze
            sentences.isEmpty() -> Phase.Loading
            else -> Phase.PickRange
        }
        /** Selected sentence indices, normalised so start <= end. */
        val range: IntRange?
            get() {
                val s = rangeStart ?: return null
                val e = rangeEnd ?: s
                return minOf(s, e)..maxOf(s, e)
            }
    }

    private val _state = MutableStateFlow(UiState(video = video))
    val state: StateFlow<UiState> = _state.asStateFlow()

    /** The latest learner take; held for analyze + FR-8 replay. */
    private var learnerSamples: FloatArray = FloatArray(0)

    init {
        viewModelScope.launch(Dispatchers.Default) {
            // Cloud source of truth: the server owns transcription, so the picker
            // must show ITS grid — the indices we pass to /analyze_video refer to
            // it. ensureVideo uploads the video first if the server doesn't have
            // it (fresh deploy), which also keeps bundled corpus + imports on the
            // same path.
            val outcome = runCatching {
                container.cloudSpeakingApi.ensureVideo(
                    video.name,
                    container.videoRepository.decodePath(video),
                ).sentences
            }
            outcome.fold(
                onSuccess = { sents -> _state.update { it.copy(sentences = sents) } },
                onFailure = { e -> _state.update { it.copy(error = e.message ?: e.toString()) } },
            )
        }
    }

    /** macOS two-click range: first click sets start, second sets end (auto-swapped). */
    fun pickSentence(idx: Int) {
        _state.update { s ->
            when {
                s.rangeStart == null -> s.copy(rangeStart = idx, rangeEnd = null)
                s.rangeEnd == null -> s.copy(rangeEnd = idx)
                else -> s.copy(rangeStart = idx, rangeEnd = null) // restart a new range
            }
        }
    }

    /** Enter the studio once at least a range start is set. */
    fun enterStudio() {
        _state.update { it.copy(studioEntered = it.rangeStart != null) }
    }

    fun backToPick() {
        _state.update { it.copy(studioEntered = false) }
    }

    /** Video-relative [start, end] for the selected range, or null. */
    fun selectedSpan(): Pair<Double, Double>? {
        val s = _state.value
        val r = s.range ?: return null
        val start = s.sentences[r.first].start.toDouble()
        val end = s.sentences[r.last].end.toDouble()
        return start to end
    }

    fun startRecording() {
        if (_state.value.isRecording) return
        container.learnerRecorder.start()
        _state.update { it.copy(isRecording = true, hasTake = false, result = null, error = null) }
    }

    fun stopRecording() {
        if (!_state.value.isRecording) return
        learnerSamples = container.learnerRecorder.stop()
        _state.update { it.copy(isRecording = false, hasTake = learnerSamples.isNotEmpty()) }
    }

    fun analyze() {
        val span = selectedSpan() ?: return
        val range = _state.value.range ?: return
        if (learnerSamples.isEmpty()) return
        _state.update { it.copy(isAnalyzing = true, error = null) }
        viewModelScope.launch(Dispatchers.Default) {
            val outcome = runCatching {
                analyzeCloud(span, range, learnerSamples)
            }
            outcome.fold(
                onSuccess = { res -> _state.update { it.copy(isAnalyzing = false, result = res) } },
                onFailure = { e -> _state.update { it.copy(isAnalyzing = false, error = e.message ?: e.toString()) } },
            )
        }
    }

    /** Skip the mic and feed the decoded reference back as the learner take
     *  — same-voice identity, expect ~95.0 accuracy. Useful on the emulator where
     *  the microphone delivers clipped garbage (CaptureProbeDeviceTest). */
    fun demoAnalyze() {
        val span = selectedSpan() ?: return
        val range = _state.value.range ?: return
        _state.update { it.copy(isAnalyzing = true, error = null) }
        viewModelScope.launch(Dispatchers.Default) {
            val outcome = runCatching {
                val ref = container.videoRepository.decodeReferenceSegment(video, span.first, span.second)
                learnerSamples = ref.samples
                analyzeCloud(span, range, ref.samples)
            }
            outcome.fold(
                onSuccess = { res -> _state.update { it.copy(isAnalyzing = false, result = res, hasTake = true) } },
                onFailure = { e -> _state.update { it.copy(isAnalyzing = false, error = e.message ?: e.toString()) } },
            )
        }
    }

    /**
     * The cloud path (shared by [analyze] and [demoAnalyze]): upload the take as
     * 16 kHz PCM16 WAV, let the server score + align + run FR-11 phoneme
     * diagnosis, then decode the reference locally (the video is on-device) for
     * A/B replay and map the server's clip-relative times onto the pre-rolled
     * decode. Learner spans come back relative to the uploaded take, so they
     * index [take] directly.
     */
    private suspend fun analyzeCloud(
        span: Pair<Double, Double>,
        range: IntRange,
        take: FloatArray,
    ): AnalysisResult {
        val cloud = container.cloudSpeakingApi.analyzeRange(
            videoName = video.name,
            startIndex = range.first,
            endIndex = range.last,
            learnerWav = WavEncoder.encodePcm16(take),
        )
        val ref: DecodedAudio = container.videoRepository.decodeReferenceSegment(video, span.first, span.second)
        val mapped = cloud.remapToLocalReference(span.first, ref.startS)
        return AnalysisResult(
            overallScore = mapped.overallScore,
            overallBand = mapped.overallBand,
            accuracy = mapped.accuracy,
            fluency = mapped.fluency,
            speechRateRatio = mapped.speechRateRatio,
            tips = mapped.tips,
            sentences = mapped.sentences,
            refSamples = ref.samples,
            learnerSamples = take,
        )
    }

    fun resetResult() {
        _state.update { it.copy(result = null) }
    }

    fun dismissError() {
        _state.update { it.copy(error = null) }
    }

    /** FR-8 reference clip for a word/sentence span (startS-relative into the result's refSamples). */
    fun playReference(startS: Float, endS: Float) {
        _state.value.result?.let { container.clipPlayer.playClip(it.refSamples, startS, endS) }
    }

    /** FR-8 learner clip for a word/sentence span (relative into the result's learnerSamples). */
    fun playLearner(startS: Float, endS: Float) {
        _state.value.result?.let { container.clipPlayer.playClip(it.learnerSamples, startS, endS) }
    }

    fun stopClips() = container.clipPlayer.stop()
}
