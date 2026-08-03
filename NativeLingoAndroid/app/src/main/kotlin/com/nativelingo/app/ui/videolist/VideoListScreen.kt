package com.nativelingo.app.ui.videolist

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.nativelingo.app.di.AppContainer
import com.nativelingo.app.repo.VideoRepository
import com.nativelingo.app.ui.theme.LocalNativeLingoColors
import com.nativelingo.app.warmup.Warmup

@Composable
fun VideoListScreen(container: AppContainer, onPick: (VideoRepository.CorpusVideo) -> Unit) {
    val vm: VideoListViewModel = viewModel { VideoListViewModel(container) }
    val state by vm.state.collectAsStateWithLifecycle()
    val warmup by vm.warmup.collectAsStateWithLifecycle()
    val brand = LocalNativeLingoColors.current
    val ctx = LocalContext.current

    val safPick = rememberLauncherForActivityResult(
        androidx.activity.result.contract.ActivityResultContracts.GetContent()
    ) { uri -> if (uri != null) vm.importVideo(uri) }

    // No per-screen TopAppBar — the floating WorkbenchTopBar (brand + module
    // switcher) is app-shell-level, defined in AppNavHost. This screen just
    // leaves top clearance for it.
    Column(
        Modifier
            .fillMaxSize()
            .statusBarsPadding()
            .padding(top = 64.dp)
            .padding(horizontal = 16.dp),
    ) {
        Text("选择参考视频", style = MaterialTheme.typography.titleLarge, color = brand.ink)
        Text(
            "选一段视频 → 选句子 → 跟读录音 → 看发音准确度与逐词改进建议。全程离线。",
            color = brand.muted, style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(top = 4.dp, bottom = 8.dp),
        )
        WarmupStatus(warmup)

        if (state.needsActivation) {
            ActivationCard(
                isActivating = state.isActivating,
                error = state.activationError,
                onActivate = vm::activate,
            )
        }

        if (state.import.isImporting) {
            Column(Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
                Text(state.import.stage, color = brand.muted)
                LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
            }
        }
        if (state.import.error != null) {
            Text("导入失败:${state.import.error}", color = brand.danger)
            OutlinedButton(onClick = vm::dismissImportError) { Text("关闭") }
        }

        // Inline import button (was a FAB; the FAB collided with the floating topbar).
        val importInteraction = remember { MutableInteractionSource() }
        Text(
            "导入视频",
            style = MaterialTheme.typography.labelLarge,
            color = brand.surface,
            modifier = Modifier
                .padding(vertical = 8.dp)
                .clip(RoundedCornerShape(11.dp))
                .background(brand.ink)
                .clickable(interactionSource = importInteraction, indication = null) { safPick.launch("video/*") }
                .padding(horizontal = 17.dp, vertical = 12.dp),
        )

        when {
            state.listError != null -> Text("读取素材出错:${state.listError}", color = brand.danger)
            state.videos.isEmpty() && !state.import.isImporting -> Text(
                "没有素材。点上方“导入视频”,或把 *.mp4 放进 videos/ 后重新构建。",
                color = brand.muted,
            )
            else -> LazyColumn(
                modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(state.videos) { v ->
                    Column(
                        Modifier
                            .fillMaxWidth()
                            .clickable { onPick(v) }
                            .drawCard(brand)
                            .padding(14.dp),
                    ) {
                            Text(v.name, style = MaterialTheme.typography.titleLarge, color = brand.ink)
                            val dur = "时长 %d:%02d".format((v.durationS / 60).toInt(), (v.durationS % 60).toInt())
                            val source = if (v.importPath != null) " · 已导入" else " · 内置"
                            Text(dur + source, color = brand.muted, style = MaterialTheme.typography.bodyMedium)
                        }
                    }
                }
            }
        }
    }

@Composable
private fun WarmupStatus(state: Warmup.State) {
    val brand = LocalNativeLingoColors.current
    when (state) {
        Warmup.State.Idle -> Text("准备模型…", color = brand.muted)
        is Warmup.State.Copying -> {
            val frac = if (state.totalBytes > 0) state.doneBytes.toFloat() / state.totalBytes else 0f
            Column(Modifier.fillMaxWidth().padding(top = 8.dp)) {
                Text("解压模型 %d%%".format((frac * 100).toInt()), color = brand.muted)
                LinearProgressIndicator(progress = { frac }, modifier = Modifier.fillMaxWidth())
            }
        }
        is Warmup.State.Verifying -> {
            val frac = if (state.totalBytes > 0) state.doneBytes.toFloat() / state.totalBytes else 0f
            Column(Modifier.fillMaxWidth().padding(top = 8.dp)) {
                Text("校验模型 %d%%".format((frac * 100).toInt()), color = brand.muted)
                LinearProgressIndicator(progress = { frac }, modifier = Modifier.fillMaxWidth())
            }
        }
        Warmup.State.Ready -> Text("模型就绪 ✓", color = brand.good)
        is Warmup.State.Error -> Text("模型未就位:${state.message}\n用 scripts/push_device_models.sh 推送模型。", color = brand.bad)
    }
}

/** A flat card: brand-card fill + hairline border, 14 dp radius. */
private fun Modifier.drawCard(brand: com.nativelingo.app.ui.theme.NativeLingoColors): Modifier =
    this.background(brand.surface, RoundedCornerShape(14.dp))
        .border(1.dp, brand.line, RoundedCornerShape(14.dp))

/**
 * Cloud account sign-in (v0.7.2): the APK ships with no server credential,
 * so the first run (or a revoked token) asks for an account. The user logs
 * in with an existing account or registers a new one — the server verifies
 * the password and issues this device's token.
 */
@Composable
private fun ActivationCard(
    isActivating: Boolean,
    error: String?,
    onActivate: (username: String, password: String, register: Boolean) -> Unit,
) {
    val brand = LocalNativeLingoColors.current
    var username by remember { androidx.compose.runtime.mutableStateOf("") }
    var password by remember { androidx.compose.runtime.mutableStateOf("") }
    Column(
        Modifier
            .fillMaxWidth()
            .padding(top = 12.dp)
            .drawCard(brand)
            .padding(14.dp),
    ) {
        Text("登录云端账号", style = MaterialTheme.typography.titleMedium, color = brand.ink)
        Text(
            "评分服务在你自己的服务器上。注册一次账号，以后所有设备用同一账号登录即可。",
            color = brand.muted, style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(top = 4.dp, bottom = 10.dp),
        )
        androidx.compose.material3.OutlinedTextField(
            value = username,
            onValueChange = { username = it },
            label = { Text("用户名") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        androidx.compose.material3.OutlinedTextField(
            value = password,
            onValueChange = { password = it },
            label = { Text("密码") },
            singleLine = true,
            visualTransformation = androidx.compose.ui.text.input.PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
        )
        if (error != null) {
            Text(error, color = brand.danger, style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(top = 6.dp))
        }
        Row(Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedButton(
                onClick = { onActivate(username, password, false) },
                enabled = !isActivating && username.isNotBlank() && password.isNotBlank(),
            ) {
                Text(if (isActivating) "登录中…" else "登录")
            }
            OutlinedButton(
                onClick = { onActivate(username, password, true) },
                enabled = !isActivating && username.isNotBlank() && password.isNotBlank(),
            ) {
                Text("注册新账号")
            }
        }
    }
}
