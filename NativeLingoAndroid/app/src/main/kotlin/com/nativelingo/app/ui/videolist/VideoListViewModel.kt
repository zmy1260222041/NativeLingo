package com.nativelingo.app.ui.videolist

import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.nativelingo.app.di.AppContainer
import com.nativelingo.app.repo.ImportRepository.ImportProgress
import com.nativelingo.app.repo.VideoRepository
import com.nativelingo.app.warmup.Warmup
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

class VideoListViewModel(private val container: AppContainer) : ViewModel() {

    data class ImportState(
        val isImporting: Boolean = false,
        val stage: String = "",
        val error: String? = null,
    )

    data class UiState(
        val videos: List<VideoRepository.CorpusVideo> = emptyList(),
        val import: ImportState = ImportState(),
        val listError: String? = null,
        /** Cloud device activation (v0.7.1): true until a device token exists. */
        val needsActivation: Boolean = false,
        val isActivating: Boolean = false,
        val activationError: String? = null,
    )

    private val _state = MutableStateFlow(UiState())
    val state: StateFlow<UiState> = _state.asStateFlow()
    val warmup: StateFlow<Warmup.State> get() = container.warmup.state

    init {
        container.warmup.start()
        // The cloud speaking track needs a registered device token; the APK
        // ships with no credential, so a fresh install starts unactivated.
        if (container.tokenStore.loadToken() == null) {
            _state.update { it.copy(needsActivation = true) }
        }
        refreshList()
    }

    /** POST /register with an operator-issued one-time code; stores the token. */
    fun activate(code: String) {
        if (code.isBlank() || _state.value.isActivating) return
        _state.update { it.copy(isActivating = true, activationError = null) }
        viewModelScope.launch(Dispatchers.Default) {
            val outcome = runCatching {
                val token = container.cloudSpeakingApi.register(
                    container.tokenStore.deviceId(),
                    code.trim(),
                )
                container.tokenStore.saveToken(token)
            }
            outcome.fold(
                onSuccess = {
                    _state.update { it.copy(isActivating = false, needsActivation = false) }
                    refreshList()
                },
                onFailure = { e ->
                    _state.update {
                        it.copy(isActivating = false, activationError = e.message ?: e.toString())
                    }
                },
            )
        }
    }

    /** A revoked/expired device token surfaces as 401s — drop it and re-activate. */
    fun handleAuthError() {
        container.tokenStore.clear()
        _state.update { it.copy(needsActivation = true, listError = null) }
    }

    fun refreshList() {
        viewModelScope.launch(Dispatchers.Default) {
            val outcome = runCatching {
                val bundled = container.videoRepository.listBundled()
                val imported = container.importRepository.listImported()
                bundled + imported
            }
            outcome.fold(
                onSuccess = { vids -> _state.update { it.copy(videos = vids, listError = null) } },
                onFailure = { e -> _state.update { it.copy(listError = e.message ?: e.toString()) } },
            )
        }
    }

    fun importVideo(uri: Uri) {
        val repo = container.importRepository
        _state.update { it.copy(import = ImportState(isImporting = true, stage = "复制中…")) }
        viewModelScope.launch {
            val outcome = repo.importVideo(uri) { prog ->
                val label = when (prog) {
                    is ImportProgress.Copying -> "复制中…"
                    is ImportProgress.Uploading -> "上传到云端…"
                    is ImportProgress.Transcribing -> "云端转写中…"
                    is ImportProgress.Segmenting -> "切句…"
                }
                _state.update { it.copy(import = ImportState(isImporting = true, stage = label)) }
            }
            outcome.fold(
                onSuccess = {
                    _state.update { it.copy(import = ImportState(isImporting = false)) }
                    refreshList()
                },
                onFailure = { e ->
                    _state.update { it.copy(import = ImportState(error = e.message ?: e.toString())) }
                },
            )
        }
    }

    fun dismissImportError() {
        _state.update { it.copy(import = ImportState()) }
    }
}
