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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
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
import androidx.compose.ui.graphics.Color
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
import com.nativelingo.app.di.AppContainer
import com.nativelingo.app.ui.theme.LocalNativeLingoColors
import com.nativelingo.vision.YoloDetector
import kotlin.math.roundToInt

/**
 * The Memorizing (识物) screen — phase-1 slice: upload → YOLOE recognition →
 * clickable object hotspots + a count ribbon. The desktop workbench's editorial
 * split becomes a single-column flow on mobile: the photo fills the width and
 * the detection overlay sits on top of it.
 *
 * The detail inspector (parts / 跟读 / 情景) is staged for later phases; tapping
 * a hotspot in phase 1 is a no-op confirmation that the box is tappable.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MemorizeScreen(container: AppContainer) {
    val vm: MemorizeViewModel = viewModel { MemorizeViewModel(container) }
    val state by vm.state.collectAsStateWithLifecycle()
    val brand = LocalNativeLingoColors.current
    val ctx = LocalContext.current

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
                "选一张照片 → 离线识别物体 → 看英文。点击物体进入跟读（即将上线）。",
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
                    onReset = vm::reset,
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
    onReset: () -> Unit,
) {
    // The object-count ribbon: {label_en: count}, desktop `countObjectLabels`.
    val counts = remember(stage.objects) {
        stage.objects.groupingBy { it.labelEn }.eachCount().entries.sortedByDescending { it.value }
    }

    // Detection overlay needs the bitmap's actual rendered box (ContentScale.Fit
    // letterboxes the image inside the composable). Computed in the layout below
    // and passed to the overlay via the remembered mapping closure.
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        DetectionCanvas(brand, stage.bitmap, stage.objects)

        if (counts.isNotEmpty()) {
            Text(
                "识别到 ${stage.objects.size} 个物体",
                color = brand.text,
                style = MaterialTheme.typography.titleSmall,
            )
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                counts.forEach { (label, count) ->
                    ObjectChip(brand, labelEn = label, count = count)
                }
            }
        } else {
            Text("没有识别到物体。换一张照片试试。", color = brand.muted)
        }

        OutlinedButton(onClick = onReset) { Text("换张照片") }
    }
}

@Composable
private fun DetectionCanvas(
    brand: com.nativelingo.app.ui.theme.NativeLingoColors,
    bitmap: Bitmap,
    objects: List<YoloDetector.Detection>,
) {
    val imageBmp = remember(bitmap) { bitmap.asImageBitmap() }
    val imgW = bitmap.width.toFloat()
    val imgH = bitmap.height.toFloat()
    val accent = brand.accent
    val dashed = remember { PathEffect.dashPathEffect(floatArrayOf(12f, 8f)) }

    Box(
        Modifier
            .fillMaxWidth()
            .aspectRatio(imgW / imgH)
            .drawCard(brand),
    ) {
        // The image is rendered Fit into a Box whose aspect ratio already matches
        // the bitmap's, so it fills the box edge-to-edge — the box-to-canvas
        // mapping is a single uniform scale, no letterbox offset to undo.
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
                        // Phase-1: tap confirms hit-testing wiring; the inspector
                        // opens in a later phase. Kept so the gesture plumbing is real.
                        val (sx, sy) = size.width / imgW to size.height / imgH
                        objects.firstOrNull { d ->
                            val x = d.box[0] * sx; val y = d.box[1] * sy
                            val w = d.box[2] * sx; val h = d.box[3] * sy
                            offset.x in x..(x + w) && offset.y in y..(y + h)
                        }
                    }
                },
        ) {
            val sx = size.width / imgW
            val sy = size.height / imgH
            objects.forEachIndexed { i, d ->
                val x = d.box[0] * sx
                val y = d.box[1] * sy
                val w = d.box[2] * sx
                val h = d.box[3] * sy
                drawRect(
                    color = accent,
                    topLeft = Offset(x, y),
                    size = Size(w, h),
                    style = androidx.compose.ui.graphics.drawscope.Stroke(width = 3f, pathEffect = dashed),
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
