package com.nativelingo.app.ui.memorize

import android.graphics.Bitmap
import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.nativelingo.app.di.AppContainer
import com.nativelingo.app.memorize.MemorizePipeline
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
 * `MEMO_STAGES` machine, phase-1 subset (`upload → analyzing → photo → error`).
 * Later phases extend [Stage] with `detail / practicing / scenario` as the
 * parts, pronounce and scenario features land.
 *
 * Heavy work runs on [Dispatchers.Default]; the only thing on the main thread
 * is Compose. Errors fold into [State.error] with a human message — the same
 * `runCatching` pattern the other screens use.
 */
class MemorizeViewModel(private val container: AppContainer) : ViewModel() {

    /** Phase-1 stage machine (desktop `MEMO_STAGES` subset). */
    sealed interface Stage {
        data object Upload : Stage
        data object Analyzing : Stage
        data class Photo(
            val photoId: String,
            val bitmap: Bitmap,
            val imageSize: IntArray,
            val objects: List<YoloDetector.Detection>,
        ) : Stage
    }

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
                        // The store was cleared mid-analysis (new upload). Drop to upload.
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

    /** Drop the current photo and return to upload. */
    fun reset() {
        container.memorizePipeline.clear()
        _state.update { it.copy(stage = Stage.Upload, error = null) }
    }

    fun dismissError() = _state.update { it.copy(error = null) }

    private fun humanError(e: Throwable): String = when (e) {
        is MemorizePipeline.MemorizeTimeout ->
            "图片识别等待超过15秒，已停止本次请求。请重试。"
        is MemorizePipeline.BadImage -> e.message ?: "图片无法识别"
        else -> e.message ?: e.toString()
    }
}
