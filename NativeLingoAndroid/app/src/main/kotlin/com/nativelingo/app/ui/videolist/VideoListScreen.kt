package com.nativelingo.app.ui.videolist

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.nativelingo.app.di.AppContainer
import com.nativelingo.app.repo.VideoRepository
import com.nativelingo.app.ui.theme.LocalNativeLingoColors
import com.nativelingo.app.warmup.Warmup

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VideoListScreen(container: AppContainer, onPick: (VideoRepository.CorpusVideo) -> Unit) {
    val vm: VideoListViewModel = viewModel { VideoListViewModel(container) }
    val state by vm.state.collectAsStateWithLifecycle()
    val warmup by vm.warmup.collectAsStateWithLifecycle()
    val brand = LocalNativeLingoColors.current

    Scaffold(topBar = { TopAppBar(title = { Text("NativeLingo") }) }) { pad ->
        Column(Modifier.fillMaxSize().padding(pad).padding(16.dp)) {
            Text("选择参考视频", style = MaterialTheme.typography.titleLarge)
            // Onboarding: a brand-new user lands on this screen with no idea what
            // the app does. One line, not a wizard.
            Text(
                "选一段视频 → 选句子 → 跟读录音 → 看发音准确度与逐词改进建议。全程离线。",
                color = brand.muted, style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(top = 4.dp, bottom = 8.dp),
            )
            WarmupStatus(warmup)
            when {
                state.error != null -> Text("读取素材出错:${state.error}", color = brand.bad)
                state.videos.isEmpty() -> Text("没有内置素材。把 *.mp4 放进 videos/ 后重新构建。", color = brand.muted)
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
                            Text(v.name, style = MaterialTheme.typography.titleLarge, color = brand.text)
                            Text("时长 %d:%02d".format((v.durationS / 60).toInt(), (v.durationS % 60).toInt()),
                                color = brand.muted, style = MaterialTheme.typography.bodyMedium)
                        }
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
        Warmup.State.Idle -> Text("准备校验模型…", color = brand.muted)
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
    this.background(brand.card, RoundedCornerShape(14.dp))
        .border(1.dp, brand.cardBorder, RoundedCornerShape(14.dp))
