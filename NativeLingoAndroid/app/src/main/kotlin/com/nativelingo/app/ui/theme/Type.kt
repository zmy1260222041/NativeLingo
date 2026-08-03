package com.nativelingo.app.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.ExperimentalTextApi
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import com.nativelingo.app.R

/**
 * Typography — a 1:1 port of the desktop `src/styles.css` type scale.
 *
 * Font: **Geist Variable** (the same `@fontsource-variable/geist` the macOS
 * frontend ships), bundled offline at `res/font/geist_variable.ttf`. CJK glyphs
 * fall through to the platform default (Noto Sans CJK) — Geist has no Han set,
 * and the desktop CSS does the same (`"Geist Variable", "PingFang SC", ...`).
 *
 * Two binding details from the CSS:
 *  - **Tight negative letter-spacing** on display type (`-0.045em` to `-0.075em`)
 *    is what makes headings read as editorial rather than generic.
 *  - **`font-variant-numeric: tabular-nums`** on every numeric style (scores,
 *    timers, counts, rates) via `fontFeatureSettings = "tnum"`.
 *
 * Weights use the variable axis (520/560/580/620/650/680) — Geist's `wght` axis
 * is continuous 100–900 and the desktop CSS uses these in-between values.
 */
@OptIn(ExperimentalTextApi::class)
private val Geist = FontFamily(
    Font(
        R.font.geist_variable,
        variationSettings = FontVariation.Settings(FontVariation.weight(400)),
    ),
)

/** A Geist weight at an arbitrary axis value (the variable font supports it). */
@OptIn(ExperimentalTextApi::class)
private fun geist(weight: Int): FontFamily = FontFamily(
    Font(R.font.geist_variable, variationSettings = FontVariation.Settings(FontVariation.weight(weight))),
)

/** Tabular-figures feature string, applied to every numeric style. */
private const val TNUM = "tnum"

val NativeLingoTypography = Typography(
    // ── display / hero ────────────────────────────────────────────────────────
    // .memo-intro h1: clamp(32,5.2vw,54), weight 570, tracking -0.06em, lh 0.98
    headlineLarge = TextStyle(
        fontFamily = geist(570),
        fontWeight = FontWeight.Medium,
        fontSize = 34.sp,
        lineHeight = 35.sp,
        letterSpacing = (-2.0).sp,
    ),
    // .memo-detail-label / panel-heading: clamp(22,4vw,38), weight 560, -0.045em
    headlineMedium = TextStyle(
        fontFamily = geist(560),
        fontWeight = FontWeight.Medium,
        fontSize = 24.sp,
        lineHeight = 26.sp,
        letterSpacing = (-1.1).sp,
    ),
    // .rail-heading h1 / canvas-empty strong: 17px, weight 650, -0.025em
    titleLarge = TextStyle(
        fontFamily = geist(650),
        fontWeight = FontWeight.SemiBold,
        fontSize = 17.sp,
        lineHeight = 20.sp,
        letterSpacing = (-0.4).sp,
    ),
    // .reference-text / score-track strong / dialogue en: 15px
    titleMedium = TextStyle(
        fontFamily = geist(590),
        fontWeight = FontWeight.Medium,
        fontSize = 15.sp,
        lineHeight = 22.sp,
    ),
    // .module / .tab / .inspector-tab / .btn: 13px, weight 620–650
    titleSmall = TextStyle(
        fontFamily = geist(640),
        fontWeight = FontWeight.SemiBold,
        fontSize = 13.sp,
        lineHeight = 16.sp,
    ),

    // ── body ──────────────────────────────────────────────────────────────────
    bodyLarge = TextStyle(
        fontFamily = Geist,
        fontSize = 15.sp,
        lineHeight = 22.sp,
    ),
    // .memo-intro p / sentence-item / part-chip: 12–13px
    bodyMedium = TextStyle(
        fontFamily = geist(560),
        fontWeight = FontWeight.Medium,
        fontSize = 13.sp,
        lineHeight = 19.sp,
    ),
    // .video-item .meta / .range-info / .word-tip / .object-word: 11–12px
    bodySmall = TextStyle(
        fontFamily = geist(560),
        fontWeight = FontWeight.Medium,
        fontSize = 12.sp,
        lineHeight = 17.sp,
    ),

    // ── labels / buttons ──────────────────────────────────────────────────────
    // .btn: 13px weight 650
    labelLarge = TextStyle(
        fontFamily = geist(650),
        fontWeight = FontWeight.SemiBold,
        fontSize = 13.sp,
        lineHeight = 16.sp,
    ),
    labelMedium = TextStyle(
        fontFamily = geist(590),
        fontWeight = FontWeight.Medium,
        fontSize = 12.sp,
        lineHeight = 15.sp,
    ),
    // .hotspot-tag / .video-item meta / indices: 10–11px
    labelSmall = TextStyle(
        fontFamily = geist(580),
        fontWeight = FontWeight.Medium,
        fontSize = 11.sp,
        lineHeight = 14.sp,
    ),
)

// ── numeric specials (not Material slots; used directly) ─────────────────────

/** The overall-score numeral: clamp(76,12vw,132), weight 600, -0.075em, tnum. */
val ScoreDisplay = TextStyle(
    fontFamily = geist(600),
    fontWeight = FontWeight.SemiBold,
    fontSize = 84.sp,
    lineHeight = 67.sp,
    letterSpacing = (-6.3).sp,
    fontFeatureSettings = TNUM,
)

/** A pronounce/sentence score badge value: 32px weight 580, tnum. */
val ScoreBadge = TextStyle(
    fontFamily = geist(580),
    fontWeight = FontWeight.Medium,
    fontSize = 32.sp,
    lineHeight = 32.sp,
    fontFeatureSettings = TNUM,
)

/** Timer / countdown: 13px weight 580, **positive** tracking 0.04em, tnum.
 *  The only place positive letter-spacing is used (mirrors desktop .timer). */
val TimerNumeric = TextStyle(
    fontFamily = geist(580),
    fontWeight = FontWeight.Medium,
    fontSize = 13.sp,
    letterSpacing = 0.5.sp,
    fontFeatureSettings = TNUM,
)

/** Small tabular numeric (counts, indices, rate ratio): 11–12px, tnum. */
val NumericSmall = TextStyle(
    fontFamily = geist(590),
    fontWeight = FontWeight.Medium,
    fontSize = 12.sp,
    fontFeatureSettings = TNUM,
)
