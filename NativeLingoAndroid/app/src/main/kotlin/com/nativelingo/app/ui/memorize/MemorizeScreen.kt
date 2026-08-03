package com.nativelingo.app.ui.memorize

import android.graphics.Bitmap
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.nativelingo.app.audio.ClipPlayer
import com.nativelingo.app.audio.LearnerRecorder
import com.nativelingo.app.di.AppContainer
import com.nativelingo.app.memorize.PronouncePipeline
import com.nativelingo.app.ui.theme.HotspotColors
import com.nativelingo.app.ui.theme.LocalNativeLingoColors
import com.nativelingo.app.ui.theme.NumericSmall
import com.nativelingo.app.ui.theme.ScoreBadge
import com.nativelingo.app.ui.theme.StageColors
import com.nativelingo.vision.YoloDetector

/**
 * The Memorizing (识物) screen — an editorial workbench port of the desktop
 * `#module-memorize` pane. Phase 1: upload → YOLOE → hotspots. Phase 2: tap an
 * object → hear the Piper reference → record → Track B score.
 *
 * Visual language (mirrors desktop `src/styles.css`):
 *  - The photo sits on an **always-dark stage** (`#0e0f0c`) regardless of theme.
 *  - Hotspots are **solid lime hairlines** (not dashed), brighter + filled on select.
 *  - The intro is a wide editorial hero (Geist, tight negative tracking).
 *  - Primary actions are **ink-filled**; lime is reserved for selection only.
 */
@Composable
fun MemorizeScreen(container: AppContainer) {
    val vm: MemorizeViewModel = viewModel { MemorizeViewModel(container) }
    val state by vm.state.collectAsStateWithLifecycle()
    val brand = LocalNativeLingoColors.current
    val ctx = LocalContext.current

    val clipPlayer = remember { ClipPlayer(ctx) }
    val learnerRecorder = remember { LearnerRecorder() }

    val pickImage = rememberLauncherForActivityResult(
        ActivityResultContracts.GetContent(),
    ) { uri -> if (uri != null) vm.analyze(ctx, uri) }

    Column(
        Modifier
            .fillMaxSize()
            .statusBarsPadding()
            .padding(top = 64.dp)  // clear the floating top bar
            .padding(horizontal = 16.dp),
    ) {
        when (val stage = state.stage) {
            MemorizeViewModel.Stage.Upload -> UploadStage(brand, onPick = { pickImage.launch("image/*") })
            MemorizeViewModel.Stage.Analyzing -> AnalyzingStage(brand)
            is MemorizeViewModel.Stage.Photo -> PhotoStage(
                brand = brand,
                stage = stage,
                onSelectObject = vm::selectObject,
                onReset = vm::reset,
                onPlayReference = { vm.synthesizeReference(it) },
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

        state.error?.let { err ->
            Text(
                "识别失败：$err",
                color = brand.danger,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(top = 12.dp),
            )
        }
    }
}

// ── Upload ───────────────────────────────────────────────────────────────────

@Composable
private fun UploadStage(
    brand: com.nativelingo.app.ui.theme.NativeLingoColors,
    onPick: () -> Unit,
) {
    Text(
        "把眼前事物\n变成英语",
        style = MaterialTheme.typography.headlineLarge,
        color = brand.ink,
        modifier = Modifier.padding(top = 8.dp, bottom = 10.dp),
    )
    Text(
        "拖入一张日常照片，点选物品开始探索。",
        color = brand.muted,
        style = MaterialTheme.typography.bodyMedium,
        modifier = Modifier.padding(bottom = 20.dp),
    )
    val interaction = remember { MutableInteractionSource() }
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(22.dp))
            .background(brand.surface)
            .border(1.dp, brand.lineStrong, RoundedCornerShape(22.dp))
            .clickable(interactionSource = interaction, indication = null) { onPick() }
            .padding(28.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text("拖入一张照片", style = MaterialTheme.typography.titleLarge, color = brand.ink)
        Text("JPG / PNG · 长边自动缩放到 1920px", color = brand.muted, style = MaterialTheme.typography.bodySmall)
        InkButton(onClick = onPick, label = "选择照片")
    }
}

// ── Analyzing (desktop .memo-overlay + .scan-line over a dark stage) ─────────

@Composable
private fun AnalyzingStage(brand: com.nativelingo.app.ui.theme.NativeLingoColors) {
    Text("正在识别", style = MaterialTheme.typography.headlineMedium, color = brand.ink)
    Text("本地模型处理中，无需联网。", color = brand.muted, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(top = 4.dp, bottom = 16.dp))
    // The dark photo stage with a full-bleed scrim overlay + the scan-line box
    // centered (desktop .memo-stage > .memo-overlay > .scan-line).
    Box(
        Modifier
            .fillMaxWidth()
            .aspectRatio(4f / 3f)
            .clip(RoundedCornerShape(22.dp))
            .background(StageColors.photoStage),
        contentAlignment = Alignment.Center,
    ) {
        // Scrim over the whole stage (rgba(10,11,9,0.68)).
        Box(Modifier.fillMaxSize().background(StageColors.overlayScrim))
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            ScanLine()
            Text("正在识别", color = StageColors.stageText, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

/**
 * The 110×48 scan-line box (desktop .scan-line): a 1px lime-faded frame with a
 * 1px accent line sweeping top↔bottom every 1.8s, glowing (CSS box-shadow
 * 0 0 14px accent — faked here by three stacked lines of decreasing alpha).
 */
@Composable
private fun ScanLine() {
    val transition = rememberInfiniteTransition(label = "scan")
    val t by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(1800), repeatMode = RepeatMode.Reverse),
        label = "scanT",
    )
    Canvas(Modifier.size(width = 110.dp, height = 48.dp)) {
        val w = this.size.width
        val h = this.size.height
        // Frame: 1px border, lime at 40% alpha (rgba(199,248,90,0.4)).
        drawRect(
            color = Color(red = 0.78f, green = 0.97f, blue = 0.35f, alpha = 0.4f),
            topLeft = Offset(0f, 0f),
            size = Size(w, h),
            style = androidx.compose.ui.graphics.drawscope.Stroke(width = 2f),
        )
        // Sweeping line at y = t*h. Glow = the accent line plus two wider, fainter
        // halos stacked behind it (Compose has no blur; this is the cheap stand-in).
        val lineY = t * (h - 1f)
        drawLine(StageColors.scanLine.copy(alpha = 0.18f), Offset(0f, lineY), Offset(w, lineY), strokeWidth = 7f)
        drawLine(StageColors.scanLine.copy(alpha = 0.35f), Offset(0f, lineY), Offset(w, lineY), strokeWidth = 4f)
        drawLine(StageColors.scanLine, Offset(0f, lineY), Offset(w, lineY), strokeWidth = 2f)
    }
}

// ── Photo stage ──────────────────────────────────────────────────────────────

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
    val selected = stage.objects.firstOrNull { it.id == stage.selectedObjectId }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        PhotoStageCanvas(brand, stage.bitmap, stage.objects, stage.selectedObjectId, onSelectObject)

        if (stage.objects.isNotEmpty()) {
            Text(
                "识别到 ${stage.objects.size} 个物体 · 点框选词跟读",
                style = MaterialTheme.typography.titleLarge,
                color = brand.ink,
            )
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                stage.objects.groupingBy { it.labelEn }.eachCount()
                    .entries.sortedByDescending { it.value }
                    .forEach { (label, count) -> ObjectChip(brand, label, count) }
            }
        } else {
            Text("没有识别到物体。换一张照片试试。", color = brand.muted, style = MaterialTheme.typography.bodyMedium)
        }

        selected?.let { det ->
            PronouncePanel(
                brand = brand,
                detection = det,
                pronounce = stage.pronounce,
                onPlayReference = { onPlayReference(det.labelEn) },
                onPlaySamples = onPlaySamples,
                onRecordToggle = onRecordToggle,
                isRecording = isRecording,
            )
        }

        SecondaryButton(onClick = onReset, label = "换张照片")
    }
}

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun PhotoStageCanvas(
    brand: com.nativelingo.app.ui.theme.NativeLingoColors,
    bitmap: Bitmap,
    objects: List<YoloDetector.Detection>,
    selectedObjectId: Int?,
    onSelectObject: (Int) -> Unit,
) {
    val imageBmp = remember(bitmap) { bitmap.asImageBitmap() }
    val imgW = bitmap.width.toFloat()
    val imgH = bitmap.height.toFloat()
    val density = androidx.compose.ui.platform.LocalDensity.current
    // Actual measured size of the stage. BoxWithConstraints' maxWidth/maxHeight
    // are unreliable at first composition (loose constraints), so capture the
    // real pixel size via onSizeChanged — the single source both the boxes and
    // the label flags map through.
    var stagePx by remember { androidx.compose.runtime.mutableStateOf(androidx.compose.ui.geometry.Size.Zero) }
    val sx = if (stagePx.width > 0f) stagePx.width / imgW else 0f
    val sy = if (stagePx.height > 0f) stagePx.height / imgH else 0f
    val tagPx = with(density) { 25.dp.toPx() }

    Box(
        Modifier
            .fillMaxWidth()
            .aspectRatio(imgW / imgH)
            .onSizeChanged { stagePx = androidx.compose.ui.geometry.Size(it.width.toFloat(), it.height.toFloat()) }
            .clip(RoundedCornerShape(22.dp))
            .background(StageColors.photoStage),
    ) {
        Image(
            bitmap = imageBmp,
            contentDescription = "待识别照片",
            contentScale = ContentScale.Fit,
            modifier = Modifier.fillMaxSize(),
        )

        // Boxes + tap layer.
        Canvas(
            Modifier
                .fillMaxSize()
                .pointerInput(objects, sx, sy) {
                    detectTapGestures { offset ->
                        objects.firstOrNull { d ->
                            val x = d.box[0] * sx; val y = d.box[1] * sy
                            val w = d.box[2] * sx; val h = d.box[3] * sy
                            offset.x in x..(x + w) && offset.y in y..(y + h)
                        }?.let { onSelectObject(it.id) }
                    }
                },
        ) {
            objects.forEach { d ->
                val x = d.box[0] * sx; val y = d.box[1] * sy
                val w = d.box[2] * sx; val h = d.box[3] * sy
                val isSelected = d.id == selectedObjectId
                drawRect(
                    color = if (isSelected) brand.accent else HotspotColors.border,
                    topLeft = Offset(x, y),
                    size = Size(w, h),
                    style = androidx.compose.ui.graphics.drawscope.Stroke(width = if (isSelected) 4f else 2f),
                )
                if (isSelected) drawRect(HotspotColors.activeFill, Offset(x, y), Size(w, h))
            }
        }

        // Label flags above each box (desktop .hotspot-tag). Weak by default,
        // fully revealed when selected — "labels are weak by default" (design doc).
        // Dp offsets (not the lambda form): the lambda is evaluated at layout
        // time with possibly-stale captures; the Dp form recomposes with the
        // measured size.
        objects.forEach { d ->
            val x = (d.box[0] * sx).toInt()
            val y = (d.box[1] * sy - tagPx).toInt()
            HotspotTag(
                label = d.labelEn,
                accent = brand.accent,
                accentInk = brand.accentInk,
                revealed = d.id == selectedObjectId,
                modifier = Modifier.offset(x = with(density) { x.toDp() }, y = with(density) { y.toDp() }),
            )
        }
    }
}

/**
 * The label flag above a hotspot (desktop .hotspot-tag): accent fill, accent-ink
 * text, asymmetric corner radius (sharp bottom-left, like a tag pinned at the
 * box's top-left). Opacity is 0.2 by default and snaps to 1.0 when selected.
 */
@Composable
private fun HotspotTag(
    label: String,
    accent: Color,
    accentInk: Color,
    revealed: Boolean,
    modifier: Modifier = Modifier,
) {
    // Desktop sets the whole flag to opacity 0.2 when idle ("labels are weak by
    // default") and 1.0 on selection. On the desktop the photo stage is always
    // dark, so 0.2 of lime is still legible. Android photos fill the stage (no
    // dark backdrop shows), so 0.2 of lime over a light photo is invisible —
    // the idle floor is raised to 0.75 (weak but legible), full on selection.
    val alpha by androidx.compose.animation.core.animateFloatAsState(
        targetValue = if (revealed) 1f else 0.75f,
        animationSpec = androidx.compose.animation.core.tween(180),
        label = "tagAlpha",
    )
    Text(
        text = label,
        style = MaterialTheme.typography.labelSmall,
        color = accentInk,
        modifier = modifier
            .graphicsLayer { this.alpha = alpha }
            .clip(RoundedCornerShape(topStart = 6.dp, topEnd = 6.dp, bottomEnd = 6.dp, bottomStart = 0.dp))
            .background(accent)
            .border(1.dp, accentInk.copy(alpha = 0.35f), RoundedCornerShape(topStart = 6.dp, topEnd = 6.dp, bottomEnd = 6.dp, bottomStart = 0.dp))
            .padding(horizontal = 7.dp, vertical = 5.dp),
    )
}

// ── Pronounce panel ──────────────────────────────────────────────────────────

@Composable
private fun PronouncePanel(
    brand: com.nativelingo.app.ui.theme.NativeLingoColors,
    detection: YoloDetector.Detection,
    pronounce: MemorizeViewModel.PronounceState,
    onPlayReference: () -> Unit,
    onPlaySamples: (FloatArray, Int) -> Unit,
    onRecordToggle: () -> Unit,
    isRecording: Boolean,
) {
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(brand.surfaceRaised)
            .border(1.dp, brand.line, RoundedCornerShape(14.dp))
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(detection.labelEn, style = MaterialTheme.typography.headlineMedium, color = brand.ink)
        Text(detection.labelZh, color = brand.muted, style = MaterialTheme.typography.bodyMedium)

        if (pronounce.isSynthesizing) {
            Text("合成参考音频…", color = brand.muted, style = MaterialTheme.typography.bodyMedium)
            LinearProgressIndicator(modifier = Modifier.fillMaxWidth(), color = brand.accent)
        } else {
            val ref = pronounce.referenceSamples
            SecondaryButton(
                onClick = { if (ref != null) onPlaySamples(ref, pronounce.referenceSampleRate) else onPlayReference() },
                label = if (ref == null) "生成并播放参考" else "播放参考",
            )
        }

        RecordButton(
            brand = brand,
            recording = isRecording,
            enabled = !pronounce.isScoring && !pronounce.isSynthesizing && pronounce.referenceSamples != null,
            onClick = onRecordToggle,
        )

        if (pronounce.isScoring) {
            Text("评分中…", color = brand.muted, style = MaterialTheme.typography.bodyMedium)
            LinearProgressIndicator(modifier = Modifier.fillMaxWidth(), color = brand.accent)
        }
        pronounce.score?.let { ScoreReadout(brand, it) }
    }
}

@Composable
private fun RecordButton(
    brand: com.nativelingo.app.ui.theme.NativeLingoColors,
    recording: Boolean,
    enabled: Boolean,
    onClick: () -> Unit,
) {
    val interaction = remember { MutableInteractionSource() }
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(
            Modifier
                .size(54.dp)
                .clip(RoundedCornerShape(50))
                .background(if (recording) brand.record else brand.recordSoft)
                .border(1.dp, brand.record.copy(alpha = 0.34f), RoundedCornerShape(50))
                .clickable(interactionSource = interaction, indication = null, enabled = enabled) { onClick() },
            contentAlignment = Alignment.Center,
        ) {
            Canvas(Modifier.size(20.dp)) {
                if (recording) drawRect(brand.surface) else drawCircle(brand.record)
            }
        }
        Text(
            if (recording) "停止并评分" else "录音跟读",
            style = MaterialTheme.typography.labelLarge,
            color = if (enabled) brand.ink else brand.faint,
        )
    }
}

@Composable
private fun ScoreReadout(brand: com.nativelingo.app.ui.theme.NativeLingoColors, s: PronouncePipeline.Score) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        ScoreBadge(brand, "准确度", s.accuracy, Modifier.weight(1f))
        ScoreBadge(brand, "流畅度", s.fluency, Modifier.weight(1f))
    }
    Text(
        "语速比 ${"%.2f".format(s.speechRateRatio)}（1.0 = 与参考一致）",
        color = brand.muted,
        style = NumericSmall,
        modifier = Modifier.padding(top = 2.dp),
    )
}

@Composable
private fun ScoreBadge(
    brand: com.nativelingo.app.ui.theme.NativeLingoColors,
    label: String,
    value: Float,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier
            .clip(RoundedCornerShape(14.dp))
            .background(brand.surface)
            .border(1.dp, brand.line, RoundedCornerShape(14.dp))
            .padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Text(label, color = brand.muted, style = MaterialTheme.typography.labelSmall)
        Text("%.1f".format(value), color = brand.bandFor(value), style = ScoreBadge)
    }
}

// ── shared buttons ───────────────────────────────────────────────────────────

@Composable
private fun InkButton(onClick: () -> Unit, label: String) {
    Button(
        onClick = onClick,
        colors = ButtonDefaults.buttonColors(
            containerColor = MaterialTheme.colorScheme.primary,
            contentColor = MaterialTheme.colorScheme.onPrimary,
        ),
        shape = RoundedCornerShape(11.dp),
    ) { Text(label, style = MaterialTheme.typography.labelLarge) }
}

@Composable
private fun SecondaryButton(onClick: () -> Unit, label: String) {
    val brand = LocalNativeLingoColors.current
    val interaction = remember { MutableInteractionSource() }
    Text(
        label,
        style = MaterialTheme.typography.labelLarge,
        color = brand.ink,
        modifier = Modifier
            .clip(RoundedCornerShape(11.dp))
            .background(brand.surface)
            .border(1.dp, brand.lineStrong, RoundedCornerShape(11.dp))
            .clickable(interactionSource = interaction, indication = null) { onClick() }
            .padding(horizontal = 17.dp, vertical = 12.dp),
    )
}

@Composable
private fun ObjectChip(
    brand: com.nativelingo.app.ui.theme.NativeLingoColors,
    labelEn: String,
    count: Int,
) {
    Column(
        Modifier
            .clip(RoundedCornerShape(9.dp))
            .background(brand.surface)
            .border(1.dp, brand.line, RoundedCornerShape(9.dp))
            .padding(horizontal = 12.dp, vertical = 7.dp),
    ) {
        Text(labelEn, color = brand.inkSoft, fontSize = 11.sp, fontWeight = FontWeight.Medium)
        Text("×$count", color = brand.muted, style = NumericSmall)
    }
}
