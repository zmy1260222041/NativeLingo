package com.nativelingo.app.ui.theme

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

private val NativeLingoDarkScheme = darkColorScheme(
    primary = Accent,
    background = Bg,
    surface = Card,
    surfaceVariant = Card,
    outline = CardBorder,
    onPrimary = Text,
    onBackground = Text,
    onSurface = Text,
    onSurfaceVariant = Muted,
    error = Bad,
)

/**
 * The app theme. Dark-only — the macOS frontend (src/styles.css) has no light
 * variant, and the score-band colours are tuned for the dark bg — so
 * [isSystemInDarkTheme] is intentionally ignored. Sets both the Material3
 * [ColorScheme] (for standard components) and the brand [NativeLingoColors]
 * (for the score bands / record / card tokens that have no Material3 slot).
 */
@Composable
fun NativeLingoTheme(content: @Composable () -> Unit) {
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = false
        }
    }
    CompositionLocalProvider(LocalNativeLingoColors provides NativeLingoColors()) {
        MaterialTheme(
            colorScheme = NativeLingoDarkScheme,
            typography = NativeLingoTypography,
            content = content,
        )
    }
}
