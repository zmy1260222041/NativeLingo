package com.nativelingo.app.ui.videolist

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.nativelingo.app.di.AppContainer
import com.nativelingo.app.repo.VideoRepository
import com.nativelingo.app.warmup.Warmup
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

class VideoListViewModel(private val container: AppContainer) : ViewModel() {

    data class UiState(
        val videos: List<VideoRepository.CorpusVideo> = emptyList(),
        val error: String? = null,
    )

    private val _state = MutableStateFlow(UiState())
    val state: StateFlow<UiState> = _state.asStateFlow()
    val warmup: StateFlow<Warmup.State> get() = container.warmup.state

    init {
        // Kick verification (idempotent) so the model-integrity bar runs on first
        // entry, then list the corpus in parallel.
        container.warmup.start()
        viewModelScope.launch(Dispatchers.Default) {
            val outcome = runCatching { container.videoRepository.listBundled() }
            outcome.fold(
                onSuccess = { vids -> _state.update { it.copy(videos = vids) } },
                onFailure = { e -> _state.update { UiState(error = e.message ?: e.toString()) } },
            )
        }
    }
}
