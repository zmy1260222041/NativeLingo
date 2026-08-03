package com.nativelingo.app.ui.memorize

import android.graphics.Bitmap
import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.nativelingo.app.di.AppContainer
import com.nativelingo.app.memorize.MemorizePipeline
import com.nativelingo.app.memorize.PronouncePipeline
import com.nativelingo.vision.YoloDetector
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * The Memorizing (识物) screen's state + intent surface — mirrors the desktop
 * `MEMO_STAGES` machine.
 *
 * Phase 1 shipped `upload → analyzing → photo`. Phase 2 adds pronunciation
 * practice (FR-17) under [Stage.Photo]: tapping an object selects it, then the
 * user can hear the Piper reference, record themselves, and get a Track B
 * score. [PronounceState] holds the per-object practice state so switching
 * objects resets the score.
 *
 * Heavy work runs on [Dispatchers.Default]; the only thing on the main thread
 * is Compose. Errors fold into [State.error] with a human message — the same
 * `runCatching` pattern the other screens use.
 */
class MemorizeViewModel(private val container: AppContainer) : ViewModel() {

    sealed interface Stage {
        data object Upload : Stage
        data object Analyzing : Stage
        data class Photo(
            val photoId: String,
            val bitmap: Bitmap,
            val imageSize: IntArray,
            val objects: List<YoloDetector.Detection>,
            val selectedObjectId: Int? = null,
            val pronounce: PronounceState = PronounceState(),
        ) : Stage
    }

    /** Per-object pronunciation practice state (FR-17). Reset on object change. */
    data class PronounceState(
        val isSynthesizing: Boolean = false,
        val isScoring: Boolean = false,
        /** The 16 kHz mono reference samples (Piper output resampled), kept so the
         *  same audio is replayed and scored against — the determinism contract. */
        val referenceSamples: FloatArray? = null,
        val referenceSampleRate: Int = 16_000,
        val score: PronouncePipeline.Score? = null,
    )

    data class State(
        val stage: Stage = Stage.Upload,
        val error: String? = null,
    )

    private val _state = MutableStateFlow(State())
    val state: StateFlow<State> = _state.asStateFlow()

    /** Read the picked image into bytes off the main thread, then run the
     *  pipeline. `Uri` is only valid for the calling activity's lifetime, so the
     *  bytes are fetched before the first suspension point. */
    fun analyze(context: android.content.Context, uri: Uri) {
        _state.update { it.copy(stage = Stage.Analyzing, error = null) }
        viewModelScope.launch {
            val outcome = runCatching {
                val bytes = withContext(Dispatchers.IO) {
                    context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
                        ?: error("无法读取所选图片")
                }
                container.memorizePipeline.analyze(bytes)
            }
            outcome.fold(
                onSuccess = { result ->
                    val bitmap = container.memorizePipeline.bitmapFor(result.photoId)
                    if (bitmap == null) {
                        _state.update { it.copy(stage = Stage.Upload) }
                        return@fold
                    }
                    _state.update {
                        it.copy(
                            stage = Stage.Photo(
                                photoId = result.photoId,
                                bitmap = bitmap,
                                imageSize = result.imageSize,
                                objects = result.objects,
                            ),
                        )
                    }
                },
                onFailure = { e -> _state.update { it.copy(stage = Stage.Upload, error = humanError(e)) } },
            )
        }
    }

    /** Select/deselect an object hotspot; resets the pronounce state. */
    fun selectObject(objectId: Int) = mutatePhoto { it.copy(selectedObjectId = objectId, pronounce = PronounceState()) }
    fun clearSelection() = mutatePhoto { it.copy(selectedObjectId = null, pronounce = PronounceState()) }

    /**
     * Load the pre-rendered Piper reference clip for [text] (Option D — runtime
     * TTS is blocked by sherpa OfflineTts's reuse crash). Idempotent within a
     * selection. Returns null into the state when no clip is bundled (the UI then
     * hides the play button). The clip is already 16 kHz mono — no resampling.
     */
    fun synthesizeReference(text: String) {
        val photo = (state.value.stage as? Stage.Photo) ?: return
        if (photo.pronounce.referenceSamples != null || photo.pronounce.isSynthesizing) return
        mutatePhoto { it.copy(pronounce = it.pronounce.copy(isSynthesizing = true)) }
        viewModelScope.launch(Dispatchers.IO) {
            val clip = container.referenceClipSource.synthesize(text)
            mutatePhoto {
                it.copy(pronounce = it.pronounce.copy(
                    isSynthesizing = false,
                    referenceSamples = clip,
                    referenceSampleRate = container.referenceClipSource.sampleRate,
                ))
            }
        }
    }

    /** Score the learner's 16 kHz mono recording against the stored reference. */
    fun scoreRecording(learnerSamples: FloatArray) {
        val photo = (state.value.stage as? Stage.Photo) ?: return
        val ref = photo.pronounce.referenceSamples
        if (ref == null || photo.pronounce.isScoring) return
        mutatePhoto { it.copy(pronounce = it.pronounce.copy(isScoring = true)) }
        viewModelScope.launch(Dispatchers.Default) {
            val outcome = runCatching {
                container.pronouncePipeline.score(ref, 16_000, learnerSamples)
            }
            outcome.fold(
                onSuccess = { score ->
                    mutatePhoto { it.copy(pronounce = it.pronounce.copy(isScoring = false, score = score)) }
                },
                onFailure = { e ->
                    mutatePhoto { it.copy(pronounce = it.pronounce.copy(isScoring = false)) }
                    _state.update { s -> s.copy(error = "评分失败：${e.message ?: e.toString()}") }
                },
            )
        }
    }

    /** Drop the current photo and return to upload. */
    fun reset() {
        container.memorizePipeline.clear()
        _state.update { it.copy(stage = Stage.Upload, error = null) }
    }

    fun dismissError() = _state.update { it.copy(error = null) }

    private fun mutatePhoto(transform: (Stage.Photo) -> Stage.Photo) {
        _state.update { s ->
            val photo = s.stage as? Stage.Photo ?: return@update s
            s.copy(stage = transform(photo))
        }
    }

    private fun humanError(e: Throwable): String = when (e) {
        is MemorizePipeline.MemorizeTimeout ->
            "图片识别等待超过15秒，已停止本次请求。请重试。"
        is MemorizePipeline.BadImage -> e.message ?: "图片无法识别"
        else -> e.message ?: e.toString()
    }
}
