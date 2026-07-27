package com.nativelingo.app.ui.theme

import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

// Direct port of src/styles.css `:root` tokens (the macOS frontend's visual
// identity). The app is dark-only — the CSS has no light variant — so there is
// one palette, not a pair. The score-band thresholds (75/60) that decide which
// of good/fair/bad applies live in the results screen, not here; here are only
// the colours.

// ── surfaces & text ────────────────────────────────────────────
val Bg = Color(0xFF0F1117)          // --bg      app background
val Card = Color(0xFF1A1D27)        // --card    card fill
val CardBorder = Color(0xFF2A2E3C)  // --card-border
val Text = Color(0xFFE6E8EE)        // --text
val Muted = Color(0xFF8B90A0)       // --muted   secondary text, timestamps

// ── actions ────────────────────────────────────────────────────
val Accent = Color(0xFF5B8CFF)      // --accent       selected / in-range / primary
val AccentHover = Color(0xFF729CFF) // --accent-hover pressed state
val Record = Color(0xFFFF5B6E)      // --record       recording button

// ── score bands & word status ──────────────────────────────────
val Good = Color(0xFF4CAF82)        // --good  band ≥75, w-good
val Fair = Color(0xFFE0A64A)        // --fair  band 60–74
val Bad = Color(0xFFE05A5A)         // --bad   band <60, w-bad

// rgba tints the frontend puts behind word chips; background-tinted variants
// used in the results screen (text stays the solid colour above).
val GoodTint = Color(0x2E4CAF82)
val FairTint = Color(0x2EE0A64A)
val BadTint = Color(0x40E05A5A)
val MissedTint = Color(0x66E05A5A)

/**
 * Brand colours that have no slot in Material3's [androidx.compose.material3.ColorScheme]
 * — the score bands, the record red, the card/border surfaces the CSS uses.
 * Provided via [LocalNativeLingoColors] by [NativeLingoTheme].
 */
@Immutable
data class NativeLingoColors(
    val bg: Color = Bg,
    val card: Color = Card,
    val cardBorder: Color = CardBorder,
    val text: Color = Text,
    val muted: Color = Muted,
    val accent: Color = Accent,
    val accentHover: Color = AccentHover,
    val record: Color = Record,
    val good: Color = Good,
    val fair: Color = Fair,
    val bad: Color = Bad,
    val goodTint: Color = GoodTint,
    val fairTint: Color = FairTint,
    val badTint: Color = BadTint,
    val missedTint: Color = MissedTint,
)

val LocalNativeLingoColors = staticCompositionLocalOf { NativeLingoColors() }
