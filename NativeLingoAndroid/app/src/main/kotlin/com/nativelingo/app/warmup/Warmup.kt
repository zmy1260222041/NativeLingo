package com.nativelingo.app.warmup

import com.nativelingo.app.repo.AssetsModelSource
import com.nativelingo.models.ModelRegistry
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * First-launch model preparation: extract from APK assets (if bundled), then
 * SHA-256 verify every file. Both steps report byte progress so the UI can show
 * a determinate bar.
 *
 * Session pre-load (constructing the wav2vec2 / MMS ONNX sessions) is *not* done
 * here in M1: the [com.nativelingo.app.di.AppContainer] creates them lazily, so
 * the first analysis pays the one-time load. That is acceptable for M1; warming
 * them during verify is an optimisation to add once profiling shows it matters.
 */
class Warmup(
    private val registry: ModelRegistry,
    private val assetsSource: AssetsModelSource?,
    private val scope: CoroutineScope,
) {
    sealed interface State {
        data object Idle : State
        /** Copying models out of the APK assets (only when bundled, ~935 MiB). */
        data class Copying(val doneBytes: Long, val totalBytes: Long) : State
        /** SHA-256 verification pass (every launch, but markers skip most files). */
        data class Verifying(val doneBytes: Long, val totalBytes: Long) : State
        data object Ready : State
        data class Error(val message: String) : State
    }

    private val _state = MutableStateFlow<State>(State.Idle)
    val state: StateFlow<State> = _state.asStateFlow()

    fun start() {
        if (_state.value !is State.Idle) return
        scope.launch(Dispatchers.Default) {
            val outcome = runCatching {
                // Step 1: extract models from APK assets (no-op if already done).
                val src = assetsSource
                if (src != null) {
                    val pending = src.pendingBytes()
                    if (pending > 0) {
                        src.extractAll { done, total ->
                            _state.value = State.Copying(done, total)
                        }
                    }
                }

                // Step 2: SHA-256 verify every file in the install-time set.
                _state.value = State.Verifying(0, 0)
                registry.verifyAll { done, total -> _state.value = State.Verifying(done, total) }
            }
            _state.value = outcome.fold(
                onSuccess = { State.Ready },
                onFailure = { State.Error(it.message ?: it::class.java.simpleName) },
            )
        }
    }
}
