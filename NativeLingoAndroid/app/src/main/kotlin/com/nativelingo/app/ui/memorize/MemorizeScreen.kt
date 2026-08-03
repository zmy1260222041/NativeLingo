package com.nativelingo.app.ui.memorize

import android.graphics.Bitmap
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.nativelingo.app.audio.ClipPlayer
import com.nativelingo.app.audio.LearnerRecorder
import com.nativelingo.app.di.AppContainer
import com.nativelingo.app.ui.theme.LocalNativeLingoColors
import com.nativelingo.vision.YoloDetector
import kotlin.math.roundToInt

/**
 * The Memorizing (识物) screen. Phase 1: upload → YOLOE → hotspots + count ribbon.
 * Phase 2: tap an object → hear the Piper reference (FR-17) → record → Track B
 * score. The detail inspector's parts (探索) and scenario (情景) tabs are staged
 * for phase 4 (Qwen); this screen focuses on 跟读.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MemorizeScreen(container: AppContainer) {
    val vm: MemorizeViewModel = viewModel { MemorizeViewModel(container) }
    val state by vm.state.collectAsStateWithLifecycle()
    val brand = LocalNativeLingoColors.current
    val ctx = LocalContext.current

    // One player/recorder for the screen — reused across object selections.
    val clipPlayer = remember { ClipPlayer(ctx) }
    val learnerRecorder = remember { LearnerRecorder() }

    val pickImage = rememberLauncherForActivityResult(
        ActivityResultContracts.GetContent(),
    ) { uri -> if (uri != null) vm.analyze(ctx, uri) }

    Scaffold(
        topBar = { TopAppBar(title = { Text("识物") }) },
    ) { pad ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(pad)
                .padding(16.dp),
        ) {
            Text("把眼前事物变成英语", style = MaterialTheme.typography.titleLarge, color = brand.text)
            Text(
                "选一张照片 → 离线识别物体 → 点物体听发音并跟读。",
                color = brand.muted,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(top = 4.dp, bottom = 12.dp),
            )

            when (val stage = state.stage) {
                MemorizeViewModel.Stage.Upload -> UploadCard(brand, onPick = { pickImage.launch("image/*") })
                MemorizeViewModel.Stage.Analyzing -> AnalyzingCard(brand)
                is MemorizeViewModel.Stage.Photo -> PhotoStage(
                    brand = brand,
                    stage = stage,
                    onSelectObject = vm::selectObject,
                    onReset = vm::reset,
                    onPlayReference = { text -> vm.synthesizeReference(text) },
                    onPlaySamples = { samples, sr -> clipPlayer.playClip(samples, 0f, Float.MAX_VALUE, sr) },
                    onRecordToggle = {
                        if (learnerRecorder.isRecording) {
                            val samples = learnerRecorder.stop()
                            vm.scoreRecording(samples)
                        } else {
                            learnerRecorder.start()
                        }
                    },
                    isRecording = learnerRecorder.isRecording,
                )
            }

            if (state.error != null) {
                Text("识别失败：${state.error}", color = brand.bad, modifier = Modifier.padding(top = 12.dp))
                OutlinedButton(onClick = vm::dismissError, modifier = Modifier.padding(top = 4.dp)) {
                    Text("关闭")
                }
            }
        }
    }
}

@Composable
private fun UploadCard(brand: com.nativelingo.app.ui.theme.NativeLingoColors, onPick: () -> Unit) {
    Column(
        Modifier
            .fillMaxWidth()
            .drawCard(brand)
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text("选一张照片", style = MaterialTheme.typography.titleMedium, color = brand.text)
        Text("JPG / PNG，长边自动缩放到 1920px", color = brand.muted, style = MaterialTheme.typography.bodySmall)
        OutlinedButton(onClick = onPick) { Text("选择照片") }
    }
}

@Composable
private fun AnalyzingCard(brand: com.nativelingo.app.ui.theme.NativeLingoColors) {
    Column(
        Modifier.fillMaxWidth().drawCard(brand).padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text("正在识别…", color = brand.muted)
        LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
    }
}

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun PhotoStage(
    brand: com.nativelingo.app.ui.theme.NativeLingoColors,
    stage: MemorizeViewModel.Stage.Photo,
    onSelectObject: (Int) -> Unit,
    onReset: () -> Unit,
    onPlayReference: (String) -> Unit,
    onPlaySamples: (FloatArray, Int) -> Unit,
    onRecordToggle: () -> Unit,
    isRecording: Boolean,
) {
    val counts = remember(stage.objects) {
        stage.objects.groupingBy { it.labelEn }.eachCount().entries.sortedByDescending { it.value }
    }
    val selected = stage.objects.firstOrNull { it.id == stage.selectedObjectId }

    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        DetectionCanvas(brand, stage.bitmap, stage.objects, stage.selectedObjectId, onSelectObject)

        if (counts.isNotEmpty()) {
            Text(
                "识别到 ${stage.objects.size} 个物体 · 点框选词跟读",
                color = brand.text,
                style = MaterialTheme.typography.titleSmall,
            )
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                counts.forEach { (label, count) -> ObjectChip(brand, labelEn = label, count = count) }
            }
        } else {
            Text("没有识别到物体。换一张照片试试。", color = brand.muted)
        }

        if (selected != null) {
            PronouncePanel(
                brand = brand,
                detection = selected,
                pronounce = stage.pronounce,
                onPlayReference = { onPlayReference(selected.labelEn) },
                onPlaySamples = onPlaySamples,
                onRecordToggle = onRecordToggle,
                isRecording = isRecording,
                onClear = { /* selection cleared by tapping another or back */ },
            )
        }

        OutlinedButton(onClick = onReset) { Text("换张照片") }
    }
}

/** The selected object's pronunciation panel (FR-17): hear → record → score. */
@Composable
private fun PronouncePanel(
    brand: com.nativelingo.app.ui.theme.NativeLingoColors,
    detection: YoloDetector.Detection,
    pronounce: MemorizeViewModel.PronounceState,
    onPlayReference: () -> Unit,
    onPlaySamples: (FloatArray, Int) -> Unit,
    onRecordToggle: () -> Unit,
    isRecording: Boolean,
    onClear: () -> Unit,
) {
    Column(
        Modifier.fillMaxWidth().drawCard(brand).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text(detection.labelEn, style = MaterialTheme.typography.titleLarge, color = brand.text)
        Text(detection.labelZh, color = brand.muted, style = MaterialTheme.typography.bodyMedium)

        if (pronounce.isSynthesizing) {
            Text("合成参考音频…", color = brand.muted)
            LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
        } else {
            // First tap synthesizes; subsequent taps replay the stored reference.
            val ref = pronounce.referenceSamples
            Button(
                onClick = {
                    if (ref != null) onPlaySamples(ref, pronounce.referenceSampleRate) else onPlayReference()
                },
                enabled = !pronounce.isScoring && !isRecording,
            ) { Text(if (ref == null) "生成并播放参考" else "播放参考") }
        }

        Button(
            onClick = onRecordToggle,
            enabled = !pronounce.isScoring && !pronounce.isSynthesizing && pronounce.referenceSamples != null,
            modifier = Modifier.background(brand.record, RoundedCornerShape(14.dp)),
        ) {
            Text(if (isRecording) "■ 停止并评分" else "● 录音跟读", color = brand.text)
        }
        if (pronounce.isScoring) {
            Text("评分中…", color = brand.muted)
            LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
        }

        pronounce.score?.let { s ->
            ScoreReadout(brand, s)
        }
    }
}

@Composable
private fun ScoreReadout(brand: com.nativelingo.app.ui.theme.NativeLingoColors, s: com.nativelingo.app.memorize.PronouncePipeline.Score) {
    Column(Modifier.fillMaxWidth().padding(top = 4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        ScoreLine(brand, "准确度", s.accuracy)
        ScoreLine(brand, "流畅度", s.fluency)
        Text(
            "语速比 %.2f（1.0 = 与参考一致）".format(s.speechRateRatio),
            color = brand.muted, style = MaterialTheme.typography.bodySmall,
        )
    }
}

@Composable
private fun ScoreLine(brand: com.nativelingo.app.ui.theme.NativeLingoColors, label: String, value: Float) {
    val color = when {
        value >= 75 -> brand.good
        value >= 60 -> brand.fair
        else -> brand.bad
    }
    androidx.compose.foundation.layout.Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(label, color = brand.text, style = MaterialTheme.typography.bodyMedium)
        Text("%.1f".format(value), color = color, fontWeight = FontWeight.Bold, fontSize = 20.sp)
    }
}

@Composable
private fun DetectionCanvas(
    brand: com.nativelingo.app.ui.theme.NativeLingoColors,
    bitmap: Bitmap,
    objects: List<YoloDetector.Detection>,
    selectedObjectId: Int?,
    onSelectObject: (Int) -> Unit,
) {
    val imageBmp = remember(bitmap) { bitmap.asImageBitmap() }
    val imgW = bitmap.width.toFloat()
    val imgH = bitmap.height.toFloat()
    val accent = brand.accent
    val selectedColor = brand.good
    val dashed = remember { PathEffect.dashPathEffect(floatArrayOf(12f, 8f)) }

    Box(
        Modifier
            .fillMaxWidth()
            .aspectRatio(imgW / imgH)
            .drawCard(brand),
    ) {
        androidx.compose.foundation.Image(
            bitmap = imageBmp,
            contentDescription = "待识别照片",
            contentScale = ContentScale.Fit,
            modifier = Modifier.fillMaxSize(),
        )
        Canvas(
            Modifier
                .fillMaxSize()
                .pointerInput(objects) {
                    detectTapGestures { offset ->
                        val sx = size.width / imgW
                        val sy = size.height / imgH
                        objects.firstOrNull { d ->
                            val x = d.box[0] * sx; val y = d.box[1] * sy
                            val w = d.box[2] * sx; val h = d.box[3] * sy
                            offset.x in x..(x + w) && offset.y in y..(y + h)
                        }?.let { onSelectObject(it.id) }
                    }
                },
        ) {
            val sx = size.width / imgW
            val sy = size.height / imgH
            objects.forEach { d ->
                val x = d.box[0] * sx
                val y = d.box[1] * sy
                val w = d.box[2] * sx
                val h = d.box[3] * sy
                val isSelected = d.id == selectedObjectId
                drawRect(
                    color = if (isSelected) selectedColor else accent,
                    topLeft = Offset(x, y),
                    size = Size(w, h),
                    style = androidx.compose.ui.graphics.drawscope.Stroke(width = if (isSelected) 5f else 3f, pathEffect = dashed),
                )
            }
        }
    }
}

@Composable
private fun ObjectChip(
    brand: com.nativelingo.app.ui.theme.NativeLingoColors,
    labelEn: String,
    count: Int,
) {
    Column(
        Modifier
            .background(brand.card, RoundedCornerShape(10.dp))
            .border(1.dp, brand.cardBorder, RoundedCornerShape(10.dp))
            .padding(horizontal = 12.dp, vertical = 8.dp),
    ) {
        Text(labelEn, color = brand.text, fontSize = 15.sp, fontWeight = FontWeight.Medium)
        Text("×$count", color = brand.muted, fontSize = 12.sp)
    }
}

/** A flat card: brand-card fill + hairline border, 14 dp radius — the same
 *  surface the other screens use (see VideoListScreen.drawCard). */
private fun Modifier.drawCard(brand: com.nativelingo.app.ui.theme.NativeLingoColors): Modifier =
    this.background(brand.card, RoundedCornerShape(14.dp))
        .border(1.dp, brand.cardBorder, RoundedCornerShape(14.dp))
