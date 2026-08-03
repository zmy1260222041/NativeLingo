package com.nativelingo.app.ui.theme

import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

// ════════════════════════════════════════════════════════════════════════════
// NativeLingo brand palette — a 1:1 port of desktop/src/styles.css tokens.
//
// Desktop is light-first (warm paper canvas #f2f0ea) with a full dark variant.
// The accent is a single chartreuse lime, reserved STRICTLY for selection /
// focus / brand punctuation — never the default button color (primary buttons
// are ink-filled). Photo/video stages are ALWAYS dark regardless of theme.
//
// Two palette instances ship (Light default, Dark), selected by isSystemInDarkTheme.
// ════════════════════════════════════════════════════════════════════════════

// ── LIGHT (desktop :root default) ───────────────────────────────────────────
object LightPalette {
    val canvas = Color(0xFFF2F0EA)        // warm paper background
    val surface = Color(0xFFFAF9F5)        // primary work surface
    val surfaceRaised = Color(0xFFFFFFFF)  // raised cards / docks
    val surfaceMuted = Color(0xFFE9E8E1)   // recessed fills, segmented tracks
    val ink = Color(0xFF171814)            // primary text + primary-button fill
    val inkSoft = Color(0xFF363930)        // secondary body text
    val muted = Color(0xFF6B6F65)          // tertiary text / labels / timers
    val faint = Color(0xFF96998F)          // quaternary (timestamps, indices)
    val line = Color(0xFFD8D8CF)           // standard 1px hairline divider
    val lineStrong = Color(0xFFB9BCB1)     // stronger divider / dashed drop-zone
    val accent = Color(0xFFB7F34A)         // lime — selection, hotspot, punctuation
    val accentSoft = Color(0xFFE3F8BB)     // pale lime — selected range fill
    val accentInk = Color(0xFF1D280B)      // text on accent fill
    val record = Color(0xFFC64B45)         // recording red
    val recordSoft = Color(0xFFF5DDDA)     // record idle fill
    val warning = Color(0xFFA76422)        // amber — preparing / countdown
    val warningSoft = Color(0xFFF5E6D3)
    val danger = Color(0xFFA83D39)         // error red
    val dangerSoft = Color(0xFFF5DCDA)
    val good = Color(0xFF507D24)           // olive-green score-good
    val weak = Color(0xFFA76422)           // amber score-weak
    val bad = Color(0xFFB44640)            // red score-bad
    val focus = Color(0xFF2568D8)          // keyboard focus ring (blue)
    // Radial washes painted on the canvas (warmth carriers).
    val washAccent = Color(0x14B7F34A)     // accent-green glow, ~8% alpha
    val washOlive = Color(0x0E545C43)      // olive wash, ~5.5% alpha
}

// ── DARK (desktop .dark) ────────────────────────────────────────────────────
object DarkPalette {
    val canvas = Color(0xFF12130F)         // near-black warm
    val surface = Color(0xFF191B16)
    val surfaceRaised = Color(0xFF20231C)
    val surfaceMuted = Color(0xFF262920)
    val ink = Color(0xFFF3F2EA)            // warm white text
    val inkSoft = Color(0xFFD2D3CA)
    val muted = Color(0xFFA4A89C)
    val faint = Color(0xFF74796C)
    val line = Color(0xFF30342B)
    val lineStrong = Color(0xFF4B5044)
    val accent = Color(0xFFC7F85A)         // slightly brighter lime for dark
    val accentSoft = Color(0xFF283714)     // dark olive tint
    val accentInk = Color(0xFF172005)      // near-black on accent
    val record = Color(0xFFE66C65)
    val recordSoft = Color(0xFF3C2421)
    val warning = Color(0xFFE0A45D)
    val warningSoft = Color(0xFF3B2D1E)
    val danger = Color(0xFFEF827B)
    val dangerSoft = Color(0xFF402522)
    val good = Color(0xFFA8D96C)
    val weak = Color(0xFFE0A45D)
    val bad = Color(0xFFEF827B)
    val focus = Color(0xFF8EB8FF)
    val washAccent = Color(0x14C7F85A)
    val washOlive = Color(0x0E545C43)
}

// ── Always-dark stage colors (theme-independent) ────────────────────────────
// Photo/video stages are deliberately dark in BOTH themes (desktop .memo-stage
// bg #0e0f0c, .video-frame #0d0e0b). Pin them, do not theme-bind.
object StageColors {
    val photoStage = Color(0xFF0E0F0C)
    val videoStage = Color(0xFF0D0E0B)
    val stageText = Color(0xFFF7F7EF)      // near-white text on dark stage
    val scanLine = Color(0xFFC7F85A)       // the sweeping scan line = accent
    val overlayScrim = Color(0xAD0A0B09)   // rgba(10,11,9,0.68)
}

// ── Hotspot colors (the lime at fixed alphas, used in both themes) ──────────
// Desktop pins these as raw rgba(199,248,90,…) regardless of theme.
object HotspotColors {
    val border = Color(0xADC7F85A)         // rgba(199,248,90,0.68) — solid hairline
    val fill = Color(0x08171814)           // rgba(23,24,20,0.03)
    val activeFill = Color(0x24C7F85A)     // rgba(199,248,90,0.14)
    val candidateBorder = Color(0xC7F7F7EF)// rgba(247,247,239,0.78)
    val candidateFill = Color(0x290D0E0B)  // rgba(13,14,11,0.16)
}

/**
 * The full set of brand tokens a screen needs — every color the desktop CSS
 * exposes, in one immutable bag so a screen never reaches into two palettes.
 * Provided via [LocalNativeLingoColors] by [NativeLingoTheme], swapped on
 * isSystemInDarkTheme().
 */
@Immutable
data class NativeLingoColors(
    val canvas: Color,
    val surface: Color,
    val surfaceRaised: Color,
    val surfaceMuted: Color,
    val ink: Color,
    val inkSoft: Color,
    val muted: Color,
    val faint: Color,
    val line: Color,
    val lineStrong: Color,
    val accent: Color,
    val accentSoft: Color,
    val accentInk: Color,
    val record: Color,
    val recordSoft: Color,
    val warning: Color,
    val warningSoft: Color,
    val danger: Color,
    val dangerSoft: Color,
    val good: Color,
    val weak: Color,
    val bad: Color,
    val focus: Color,
    val washAccent: Color,
    val washOlive: Color,
) {
    companion object {
        val Light = NativeLingoColors(
            canvas = LightPalette.canvas, surface = LightPalette.surface,
            surfaceRaised = LightPalette.surfaceRaised, surfaceMuted = LightPalette.surfaceMuted,
            ink = LightPalette.ink, inkSoft = LightPalette.inkSoft,
            muted = LightPalette.muted, faint = LightPalette.faint,
            line = LightPalette.line, lineStrong = LightPalette.lineStrong,
            accent = LightPalette.accent, accentSoft = LightPalette.accentSoft, accentInk = LightPalette.accentInk,
            record = LightPalette.record, recordSoft = LightPalette.recordSoft,
            warning = LightPalette.warning, warningSoft = LightPalette.warningSoft,
            danger = LightPalette.danger, dangerSoft = LightPalette.dangerSoft,
            good = LightPalette.good, weak = LightPalette.weak, bad = LightPalette.bad,
            focus = LightPalette.focus, washAccent = LightPalette.washAccent, washOlive = LightPalette.washOlive,
        )
        val Dark = NativeLingoColors(
            canvas = DarkPalette.canvas, surface = DarkPalette.surface,
            surfaceRaised = DarkPalette.surfaceRaised, surfaceMuted = DarkPalette.surfaceMuted,
            ink = DarkPalette.ink, inkSoft = DarkPalette.inkSoft,
            muted = DarkPalette.muted, faint = DarkPalette.faint,
            line = DarkPalette.line, lineStrong = DarkPalette.lineStrong,
            accent = DarkPalette.accent, accentSoft = DarkPalette.accentSoft, accentInk = DarkPalette.accentInk,
            record = DarkPalette.record, recordSoft = DarkPalette.recordSoft,
            warning = DarkPalette.warning, warningSoft = DarkPalette.warningSoft,
            danger = DarkPalette.danger, dangerSoft = DarkPalette.dangerSoft,
            good = DarkPalette.good, weak = DarkPalette.weak, bad = DarkPalette.bad,
            focus = DarkPalette.focus, washAccent = DarkPalette.washAccent, washOlive = DarkPalette.washOlive,
        )
    }

    /** Score-band color for a 0-100 value (thresholds 75/60, desktop convention). */
    fun bandFor(score: Float): Color = when {
        score >= 75f -> good
        score >= 60f -> weak
        else -> bad
    }
}

val LocalNativeLingoColors = staticCompositionLocalOf { NativeLingoColors.Light }
