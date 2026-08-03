package com.nativelingo.app.di

import android.content.Context
import com.nativelingo.app.repo.AssetsModelSource
import com.nativelingo.app.audio.ClipPlayer
import com.nativelingo.app.audio.LearnerRecorder
import com.nativelingo.app.memorize.MemorizePipeline
import com.nativelingo.app.memorize.PronouncePipeline
import com.nativelingo.app.repo.CloudClient
import com.nativelingo.app.repo.CloudSpeakingApi
import com.nativelingo.app.repo.ImportRepository
import com.nativelingo.app.repo.TokenStore
import com.nativelingo.app.repo.RecordingsRepository
import com.nativelingo.app.repo.ReferenceClipSource
import com.nativelingo.app.repo.VideoRepository
import com.nativelingo.app.warmup.Warmup
import com.nativelingo.embed.Wav2Vec2Encoder
import com.nativelingo.models.DirectoryModelSource
import com.nativelingo.models.ModelId
import com.nativelingo.models.ModelRegistry
import com.nativelingo.vision.YoloDetector
import com.nativelingo.scoring.score.Calibration
import com.nativelingo.scoring.score.CalibrationLoader
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import java.io.File

/**
 * Manual DI root — the one object [com.nativelingo.app.NativeLingoApp] constructs
 * and hands to screens/ViewModels. Chosen over Hilt (PRD v0.4): the cores are
 * plain constructors, a ServiceLocator is one file with no ksp/Kotlin version
 * surface, and migrating later is mechanical.
 *
 * Heavy collaborators (the ONNX/sherpa sessions, the pipeline) are created lazily
 * and live for the process — exactly one wav2vec2 encoder and one MMS emitter are
 * loaded no matter how many analyses run, which is what Gate D's peak-RSS budget
 * assumes. [modelDir] mirrors where an install-time asset pack unpacks in
 * production (app-private internal storage); for M1 the weights are `adb push`-
 * delivered there by scripts/push_device_models.sh, as in R-12.
 */
class AppContainer(context: Context) {

    val appContext: Context = context.applicationContext

    /** Background scope for warmup and any one-off work that must outlive a screen. */
    val appScope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    /** `/data/data/<pkg>/files/models` — where pushed/asset-pack models land. */
    val modelDir: File = File(appContext.filesDir, "models")

    /** Checksum markers — deliberately not next to the models (R-12 harness). */
    val stateDir: File = File(appContext.filesDir, "model-state")

    /** Extracts models from APK assets on first launch; null if assets are not staged. */
    val assetsModelSource: AssetsModelSource = AssetsModelSource(appContext, modelDir)

    val registry: ModelRegistry =
        ModelRegistry(
            listOf(
                // First: models extracted from APK assets (production / GitHub release).
                assetsModelSource,
                // Fall back: adb-pushed directory (gate harness / smoke test / dev).
                DirectoryModelSource(modelDir, "pushed models (dev/gate harness)"),
            ),
            stateDir,
        )

    /** calibration.json ships on the classpath via :core-scoring's resources. */
    val calibration: Calibration by lazy { CalibrationLoader.loadDefault() }

    // ── heavy ML sessions (lazy, process-singleton) ───────────────────────────
    // Only the 识物 module's sessions remain on-device; the Speaking track's
    // encoder/aligner/whisper lived here before the cloud migration (v0.7).
    val sslEncoder: Wav2Vec2Encoder by lazy {
        Wav2Vec2Encoder(registry.resolve(ModelId.SSL_ENCODER).absolutePath)
    }
    val importRepository: ImportRepository by lazy {
        ImportRepository(appContext, cloudSpeakingApi)
    }

    // ── repos / hardware ──────────────────────────────────────────────────────
    val videoRepository: VideoRepository by lazy { VideoRepository(appContext) }
    val recordingsRepository: RecordingsRepository by lazy { RecordingsRepository(appContext) }
    val learnerRecorder: LearnerRecorder by lazy { LearnerRecorder() }

    // ── Cloud Speaking backend (Duolingo-style) ───────────────────────────────
    // Transcription, alignment, SSL scoring and FR-11 phoneme diagnosis run on
    // the self-hosted server. Auth is a per-device token (v0.7.1) — never baked
    // into the APK: the app registers on first use with an operator-issued
    // code, and the token lives encrypted in the Android Keystore. The 识物
    // module stays fully on-device — its sessions are untouched above.
    val tokenStore: TokenStore by lazy { TokenStore(appContext) }
    val cloudClient: CloudClient by lazy {
        CloudClient(appContext, tokenProvider = tokenStore::loadToken)
    }
    val cloudSpeakingApi: CloudSpeakingApi by lazy { CloudSpeakingApi(cloudClient) }

    /** One audio-clip player for FR-8 — the muted-video player is per-screen. */
    val clipPlayer: ClipPlayer by lazy { ClipPlayer(appContext) }

    // ── Memorizing (识物) module — FR-13 detection + FR-17 pronunciation. The
    // detector is resident once loaded (45 MB, like Whisper's VAD). Parts/
    // scenario (Qwen) join in phase 4. Pronunciation uses pre-rendered Piper
    // reference clips (Option D — sherpa OfflineTts crashes on reuse, issue #3675
    // class), scored by PronouncePipeline reusing the SSL encoder + DTW. ──
    val yoloDetector: YoloDetector by lazy {
        YoloDetector(registry.resolve(ModelId.YOLOE_DETECT).absolutePath)
    }
    val memorizePipeline: MemorizePipeline by lazy { MemorizePipeline(yoloDetector) }

    /** Pre-rendered Piper reference clips (FR-17). Reads wavs from APK assets —
     *  no runtime TTS, no native crash surface. 16 kHz mono PCM16. */
    val referenceClipSource: ReferenceClipSource by lazy { ReferenceClipSource(appContext) }

    /** Word/phrase pronunciation scoring (FR-17) — reuses the SSL encoder + DTW. */
    val pronouncePipeline: PronouncePipeline by lazy { PronouncePipeline(sslEncoder, calibration) }

    val warmup: Warmup by lazy { Warmup(registry, assetsModelSource, appScope) }
}
