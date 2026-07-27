package com.nativelingo.app.ui.practice

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicText
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.media3.common.MediaItem
import androidx.media3.exoplayer.ExoPlayer
import com.nativelingo.app.di.AppContainer
import com.nativelingo.app.model.AnalyzedSentence
import com.nativelingo.app.ui.theme.LocalNativeLingoColors

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PracticeScreen(container: AppContainer, videoName: String, onBack: () -> Unit) {
    val video = remember(videoName) { container.videoRepository.listBundled().first { it.name == videoName } }
    val vm: PracticeViewModel = viewModel(key = videoName) { PracticeViewModel(container, video) }
    val state by vm.state.collectAsStateWithLifecycle()
    val brand = LocalNativeLingoColors.current

    Scaffold(topBar = {
        TopAppBar(title = { Text(video.name) }, navigationIcon = {
            OutlinedButton(onClick = onBack) { Text("返回") }
        })
    }) { pad ->
        Box(Modifier.fillMaxSize().padding(pad)) {
            when (state.phase) {
                PracticeViewModel.Phase.Loading -> Center { CircularProgressIndicator() }
                PracticeViewModel.Phase.PickRange -> SentencePicker(vm, state)
                PracticeViewModel.Phase.Recording,
                PracticeViewModel.Phase.ReadyToAnalyze -> RecordStudio(container, vm, state)
                PracticeViewModel.Phase.Results -> ResultsView(vm, state)
            }
            state.error?.let { err ->
                Box(Modifier.align(Alignment.BottomCenter).padding(16.dp)) {
                    Column(Modifier.background(brand.bad).padding(12.dp)) {
                        Text(err, color = Color.White)
                        OutlinedButton(onClick = vm::dismissError) { Text("关闭") }
                    }
                }
            }
        }
    }
}

@Composable
private fun Center(content: @Composable () -> Unit) =
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { content() }

@Composable
private fun SentencePicker(vm: PracticeViewModel, state: PracticeViewModel.UiState) {
    val brand = LocalNativeLingoColors.current
    val range = state.range
    Column(Modifier.fillMaxSize()) {
        LazyColumn(
            Modifier.weight(1f).padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(vertical = 12.dp),
        ) {
            item {
                // Onboarding hint: a new user lands here with no instruction otherwise.
                Text(
                    "点一句选定起点(可再点一句扩大范围),然后点下方「去跟读」。",
                    color = brand.muted, style = MaterialTheme.typography.bodyMedium,
                )
            }
            itemsIndexed(state.sentences) { idx, s ->
                val inRange = range != null && idx in range
                val endpoint = idx == state.rangeStart || idx == state.rangeEnd
                val bg = when {
                    endpoint -> brand.accent.copy(alpha = 0.18f)
                    inRange -> brand.accent.copy(alpha = 0.08f)
                    else -> brand.card
                }
                Column(
                    Modifier.fillMaxWidth().clickable { vm.pickSentence(idx) }
                        .background(bg, RoundedCornerShape(8.dp)).padding(12.dp)
                ) {
                    Text("${idx + 1}.  %d:%02d".format((s.start / 60).toInt(), (s.start % 60).toInt()),
                        color = brand.muted, style = MaterialTheme.typography.bodyMedium)
                    Text(s.text, color = brand.text, style = MaterialTheme.typography.bodyLarge)
                }
            }
        }
        // Sticky action bar — the "去跟读" button is always on screen, not buried
        // at the end of a long list.
        androidx.compose.material3.HorizontalDivider(color = brand.cardBorder)
        Column(Modifier.fillMaxWidth().background(brand.card).padding(16.dp)) {
            Button(
                onClick = vm::enterStudio,
                enabled = state.rangeStart != null,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(
                    when {
                        state.rangeStart == null -> "先点一句"
                        state.rangeEnd == null -> "去跟读这一句"
                        else -> "去跟读选中段落"
                    }
                )
            }
        }
    }
}

// ── Recording studio ──────────────────────────────────────────────────────
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun RecordStudio(container: AppContainer, vm: PracticeViewModel, state: PracticeViewModel.UiState) {
    val brand = LocalNativeLingoColors.current
    val context = LocalContext.current
    val span = vm.selectedSpan()
    val range = state.range
    val assetUri = remember(state.video.name) { container.videoRepository.playUri(state.video) }

    // One muted-video ExoPlayer per practice entry. Clipped to [segStart, segEnd]
    // so playback stops at the range end without a position watcher.
    val exo = remember(state.video.name) {
        ExoPlayer.Builder(context).build().apply {
            setVolume(0f)
        }
    }
    DisposableEffect(state.video.name) { onDispose { exo.release() } }

    fun playMuted() {
        if (span == null) return
        val item = MediaItem.Builder()
            .setUri(assetUri)
            .setClippingConfiguration(
                MediaItem.ClippingConfiguration.Builder()
                    .setStartPositionMs((span.first * 1000).toLong())
                    .setEndPositionMs((span.second * 1000).toLong())
                    .build(),
            ).build()
        exo.setMediaItem(item)
        exo.prepare()
        exo.playWhenReady = true
    }

    val micPerm = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) { vm.startRecording(); playMuted() }
    }

    Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        // Muted video surface.
        AndroidView(
            modifier = Modifier.fillMaxWidth().aspectRatio(16f / 9f).background(Color.Black),
            factory = { ctx ->
                androidx.media3.ui.PlayerView(ctx).apply {
                    useController = false
                    player = exo
                }
            },
        )
        val refText = range?.let { state.sentences.subList(it.first, it.last + 1).joinToString(" ") { s -> s.text } }
            ?: ""
        Text(refText, color = brand.text, style = MaterialTheme.typography.bodyLarge)

        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedButton(onClick = vm::backToPick) { Text("重选句子") }
            if (state.isRecording) {
                Button(
                    onClick = { exo.pause(); vm.stopRecording() },
                    colors = ButtonDefaults.buttonColors(containerColor = brand.record),
                ) { Text("■ 停止跟读") }
            } else {
                Button(
                    onClick = { micPerm.launch(Manifest.permission.RECORD_AUDIO) },
                    colors = ButtonDefaults.buttonColors(containerColor = brand.record),
                ) { Text("● 开始跟读") }
            }
            OutlinedButton(onClick = { playMuted() }, enabled = !state.isRecording) { Text("↺ 重放画面") }
        }

        if (state.hasTake && !state.isRecording) {
            Button(
                onClick = { vm.analyze() },
                enabled = !state.isAnalyzing,
            ) {
                if (state.isAnalyzing) CircularProgressIndicator(modifier = Modifier.height(18.dp), strokeWidth = 2.dp)
                else Text("分析我的发音")
            }
        }

        // Demo affordance: skip the (broken) emulator mic and score the reference
        // against itself. Same-voice identity → ~95.0 accuracy; useful for UX
        // testing when a real mic is unavailable. Hidden once recording is used.
        if (!state.hasTake && !state.isRecording && !state.isAnalyzing) {
            OutlinedButton(onClick = { vm.demoAnalyze() }) {
                Text("调试:跳过录音,用原声试分", color = brand.muted, style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}

// ── Results ───────────────────────────────────────────────────────────────
@Composable
private fun ResultsView(vm: PracticeViewModel, state: PracticeViewModel.UiState) {
    val brand = LocalNativeLingoColors.current
    val res = state.result ?: return
    LazyColumn(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                ScoreCard("综合", res.overallScore, Modifier.weight(1f), brand)
                ScoreCard("准确度", res.accuracy, Modifier.weight(1f), brand)
                ScoreCard("流畅度", res.fluency, Modifier.weight(1f), brand)
            }
            Text("语速比(你/参考):%.2f×".format(res.speechRateRatio), color = brand.muted)
        }
        if (res.tips.isNotEmpty()) {
            item { Text("改进建议", style = MaterialTheme.typography.titleLarge, color = brand.text) }
            items(res.tips) { tip ->
                Column(Modifier.fillMaxWidth().background(brand.card, RoundedCornerShape(8.dp))
                    .border(1.dp, brand.accent, RoundedCornerShape(8.dp)).padding(12.dp)) {
                    Text(tip, color = brand.text)
                }
            }
        }
        item { Text("逐句", style = MaterialTheme.typography.titleLarge, color = brand.text) }
        items(res.sentences) { sd -> SentenceCard(vm, sd, brand) }
        item {
            OutlinedButton(onClick = vm::resetResult) { Text("再练一遍") }
        }
    }
}

@Composable
private fun ScoreCard(label: String, score: Float, modifier: Modifier, brand: com.nativelingo.app.ui.theme.NativeLingoColors) {
    val color = bandColor(score, brand)
    Column(modifier.fillMaxWidth().background(brand.card, RoundedCornerShape(10.dp))
        .border(1.dp, brand.cardBorder, RoundedCornerShape(10.dp)).padding(12.dp),
        horizontalAlignment = Alignment.CenterHorizontally) {
        Text("%.0f".format(score), color = color, style = MaterialTheme.typography.headlineLarge)
        Text(label, color = brand.muted, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun SentenceCard(vm: PracticeViewModel, s: AnalyzedSentence, brand: com.nativelingo.app.ui.theme.NativeLingoColors) {
    Column(Modifier.fillMaxWidth().background(brand.card, RoundedCornerShape(10.dp))
        .border(1.dp, brand.cardBorder, RoundedCornerShape(10.dp)).padding(12.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Text("准确 %.0f  流畅 %.0f".format(s.accuracy, s.fluency),
                color = bandColor(s.accuracy, brand))
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                OutlinedButton(onClick = { vm.playReference(s.start, s.end) }) { Text("原声") }
                if (s.learnerEnd > s.learnerStart) {
                    OutlinedButton(onClick = { vm.playLearner(s.learnerStart, s.learnerEnd) }) { Text("我的") }
                }
            }
        }
        BasicText(wordChips(s, brand), modifier = Modifier.padding(top = 8.dp))
        // Per-word tips with A/B.
        val tipped = s.words.filter { it.tip.isNotEmpty() || it.learnerEnd > it.learnerStart }
        if (tipped.isNotEmpty()) {
            Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                tipped.forEach { w ->
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(w.word, color = bandColor(w.accuracy, brand), style = MaterialTheme.typography.labelLarge)
                        if (w.tip.isNotEmpty()) Text("— " + w.tip, color = brand.text, modifier = Modifier.weight(1f))
                        OutlinedButton(onClick = { vm.playReference(w.start, w.end) }) { Text("原声") }
                        if (w.learnerEnd > w.learnerStart) {
                            OutlinedButton(onClick = { vm.playLearner(w.learnerStart, w.learnerEnd) }) { Text("我的") }
                        }
                    }
                }
            }
        }
    }
}

/** Word chips inline: each word tinted by status, missed words struck through. */
private fun wordChips(s: AnalyzedSentence, brand: com.nativelingo.app.ui.theme.NativeLingoColors): AnnotatedString =
    buildAnnotatedString {
        s.words.forEachIndexed { i, w ->
            if (i > 0) append(" ")
            val (fg, strike) = when (w.status) {
                "good" -> brand.good to false
                "weak" -> brand.fair to false
                "missed" -> brand.bad to true
                else -> brand.bad to false
            }
            withStyle(SpanStyle(color = fg, textDecoration = if (strike) TextDecoration.LineThrough else null)) {
                append(w.word)
            }
        }
    }

private fun bandColor(score: Float, brand: com.nativelingo.app.ui.theme.NativeLingoColors): Color = when {
    score >= 75f -> brand.good
    score >= 60f -> brand.fair
    else -> brand.bad
}

@Composable
private fun Spacer8() = Box(Modifier.height(8.dp))
