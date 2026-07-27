package com.nativelingo.app.warmup

import com.nativelingo.models.ModelRegistry
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * First-launch model verification — the in-process replacement for the macOS
 * `/warmup` endpoint. Runs [ModelRegistry.verifyAll] (SHA-256 over the 935 MiB
 * install-time set) off the main thread, surfacing byte progress for a bar.
 *
 * Session pre-load (constructing the wav2vec2 / MMS ONNX sessions) is *not* done
 * here in M1: the [com.nativelingo.app.di.AppContainer] creates them lazily, so
 * the first analysis pays the one-time load. That is acceptable for M1; warming
 * them during verify is an optimisation to add once profiling shows it matters.
 *
 * R-12 found that a verify marker surviving across runs made this report a hash
 * time of 0 ms ("Infinity MiB/s") — the marker is now cleared before timing, so
 * the progress here is real.
 */
class Warmup(
    private val registry: ModelRegistry,
    private val scope: CoroutineScope,
) {
    sealed interface State {
        data object Idle : State
        data class Verifying(val doneBytes: Long, val totalBytes: Long) : State
        data object Ready : State
        data class Error(val message: String) : State
    }

    private val _state = MutableStateFlow<State>(State.Idle)
    val state: StateFlow<State> = _state.asStateFlow()

    fun start() {
        if (_state.value !is State.Idle) return
        scope.launch(Dispatchers.Default) {
            _state.value = State.Verifying(0, 0)
            val outcome = runCatching {
                registry.verifyAll { done, total -> _state.value = State.Verifying(done, total) }
            }
            _state.value = outcome.fold(
                onSuccess = { State.Ready },
                onFailure = { State.Error(it.message ?: it::class.java.simpleName) },
            )
        }
    }
}
