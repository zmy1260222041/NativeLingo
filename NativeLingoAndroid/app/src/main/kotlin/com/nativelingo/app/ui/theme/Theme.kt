package com.nativelingo.app.ui.theme

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.unit.dp
import androidx.core.view.WindowCompat

// ── Material3 color schemes mapped from the brand palette ───────────────────
// Only the slots standard M3 components read are wired; everything else comes
// from NativeLingoColors via LocalNativeLingoColors. Primary = ink (so default
// Buttons are ink-filled, matching desktop .btn-primary), NOT the lime accent.

private val LightScheme: ColorScheme = lightColorScheme(
    primary = LightPalette.ink,
    onPrimary = LightPalette.surface,
    background = LightPalette.canvas,
    onBackground = LightPalette.ink,
    surface = LightPalette.surface,
    onSurface = LightPalette.ink,
    surfaceVariant = LightPalette.surfaceMuted,
    onSurfaceVariant = LightPalette.inkSoft,
    surfaceContainer = LightPalette.surface,
    surfaceContainerHigh = LightPalette.surfaceRaised,
    surfaceContainerLow = LightPalette.surfaceMuted,
    outline = LightPalette.line,
    outlineVariant = LightPalette.lineStrong,
    error = LightPalette.danger,
    onError = LightPalette.surface,
    secondary = LightPalette.inkSoft,
    onSecondary = LightPalette.surface,
    tertiary = LightPalette.accent,
    onTertiary = LightPalette.accentInk,
)

private val DarkScheme: ColorScheme = darkColorScheme(
    primary = DarkPalette.ink,
    onPrimary = DarkPalette.surface,
    background = DarkPalette.canvas,
    onBackground = DarkPalette.ink,
    surface = DarkPalette.surface,
    onSurface = DarkPalette.ink,
    surfaceVariant = DarkPalette.surfaceMuted,
    onSurfaceVariant = DarkPalette.inkSoft,
    surfaceContainer = DarkPalette.surface,
    surfaceContainerHigh = DarkPalette.surfaceRaised,
    surfaceContainerLow = DarkPalette.surfaceMuted,
    outline = DarkPalette.line,
    outlineVariant = DarkPalette.lineStrong,
    error = DarkPalette.danger,
    onError = DarkPalette.surface,
    secondary = DarkPalette.inkSoft,
    onSecondary = DarkPalette.surface,
    tertiary = DarkPalette.accent,
    onTertiary = DarkPalette.accentInk,
)

/**
 * The three canonical radii (desktop --radius-sm/md/lg). Component-level
 * overrides (10/11/12/18dp) are applied at the call site; these are the tiers
 * surfaces are built from.
 */
val NativeLingoShapes = Shapes(
    extraSmall = RoundedCornerShape(8.dp),    // --radius-sm: status pills, tooltips
    small = RoundedCornerShape(8.dp),
    medium = RoundedCornerShape(14.dp),       // --radius-md: cards, docks, inspector tabs, badges
    large = RoundedCornerShape(22.dp),        // --radius-lg: rails, canvases, stages, entry
    extraLarge = RoundedCornerShape(22.dp),
)

/**
 * The app theme — follows the system light/dark setting (desktop supports both;
 * the previous dark-only override is dropped).
 *
 * Wraps content in a [Box] painted with the warm paper canvas + two faint radial
 * color washes (accent-green top-left, olive mid-right). These washes are what
 * give the desktop its warmth — a flat background reads as generic, the washes
 * read as crafted. The full-screen SVG grain texture (desktop opacity 0.025) is
 * omitted on Android: it costs a per-frame draw for a barely-visible effect,
 * and the radial washes alone carry the intended warmth.
 *
 * Standard M3 components read the [ColorScheme] (primary = ink, so Buttons are
 * ink-filled); brand-only tokens (score bands, record red, accent, lines) come
 * from [LocalNativeLingoColors].
 */
@Composable
fun NativeLingoTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    val brand = if (darkTheme) NativeLingoColors.Dark else NativeLingoColors.Light
    val scheme = if (darkTheme) DarkScheme else LightScheme

    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            // Light theme → dark status-bar icons; dark theme → light icons.
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = !darkTheme
        }
    }

    CompositionLocalProvider(LocalNativeLingoColors provides brand) {
        MaterialTheme(
            colorScheme = scheme,
            typography = NativeLingoTypography,
            shapes = NativeLingoShapes,
        ) {
            // Warm paper canvas + radial washes behind everything.
            Box(
                Modifier
                    .fillMaxSize()
                    .paperCanvas(brand),
            ) { content() }
        }
    }
}

/** Paint the warm canvas color + the two radial washes (desktop body::before). */
private fun Modifier.paperCanvas(brand: NativeLingoColors): Modifier = drawBehind {
    drawRect(brand.canvas)
    // Accent-green glow, top-left, fading by 30rem (~ a third of the screen).
    drawRect(
        brush = Brush.radialGradient(
            center = Offset(size.width * 0.16f, size.height * 0.0f),
            radius = size.minDimension * 0.6f,
            colors = listOf(brand.washAccent, brand.canvas),
        ),
    )
    // Olive wash, mid-right.
    drawRect(
        brush = Brush.radialGradient(
            center = Offset(size.width * 0.92f, size.height * 0.42f),
            radius = size.minDimension * 0.55f,
            colors = listOf(brand.washOlive, brand.canvas),
        ),
    )
}
