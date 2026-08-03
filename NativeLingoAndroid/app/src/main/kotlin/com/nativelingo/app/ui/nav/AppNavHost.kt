package com.nativelingo.app.ui.nav

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.nativelingo.app.R
import com.nativelingo.app.di.AppContainer
import com.nativelingo.app.ui.memorize.MemorizeScreen
import com.nativelingo.app.ui.practice.PracticeScreen
import com.nativelingo.app.ui.theme.LocalNativeLingoColors
import com.nativelingo.app.ui.videolist.VideoListScreen

object Routes {
    const val VIDEOS = "videos"
    const val PRACTICE = "practice/{videoName}"
    fun practice(videoName: String) = "practice/$videoName"

    /** Top-level Memorizing (识物) destination — FR-13. */
    const val MEMORIZE = "memorize"
}

private data class TopModule(val route: String, val label: String)

private val TOP_MODULES = listOf(
    TopModule(Routes.VIDEOS, "跟读"),
    TopModule(Routes.MEMORIZE, "识物"),
)

/**
 * The app shell. A [NavHost] under a sticky [WorkbenchTopBar] that carries the
 * Goza brand mark and the 跟读 / 识物 module switcher — the Android counterpart
 * of the desktop `.topbar > .modules` segmented control.
 *
 * The switcher is a segmented pill on a recessed track; the active segment is
 * an **ink-filled inverted pill** (desktop `.module-active`), NOT the lime
 * accent — accent is reserved for selection/punctuation only. Practice is a
 * drill-in under 跟读, so the switcher hides there.
 */
@Composable
fun AppNavHost(container: AppContainer) {
    val nav = rememberNavController()
    val backStack by nav.currentBackStackEntryAsState()
    val currentRoute = backStack?.destination?.route
    val isTopLevel = currentRoute in TOP_MODULES.map { it.route }

    Box(Modifier.fillMaxWidth()) {
        NavHost(
            navController = nav,
            startDestination = Routes.VIDEOS,
        ) {
            composable(Routes.VIDEOS) {
                VideoListScreen(container, onPick = { nav.navigate(Routes.practice(it.name)) })
            }
            composable(
                route = Routes.PRACTICE,
                arguments = listOf(navArgument("videoName") { type = NavType.StringType }),
            ) { entry ->
                val videoName = entry.arguments?.getString("videoName").orEmpty()
                PracticeScreen(container, videoName, onBack = { nav.popBackStack() })
            }
            composable(Routes.MEMORIZE) {
                MemorizeScreen(container)
            }
        }

        AnimatedVisibility(
            visible = isTopLevel,
            enter = fadeIn(),
            exit = fadeOut(),
            modifier = Modifier.align(Alignment.TopCenter),
        ) {
            WorkbenchTopBar(
                modules = TOP_MODULES,
                currentRoute = currentRoute,
                showSwitcher = true,
                onSelect = { mod ->
                    if (currentRoute != mod.route) {
                        nav.navigate(mod.route) {
                            popUpTo(nav.graph.startDestinationId) { saveState = true }
                            launchSingleTop = true
                            restoreState = true
                        }
                    }
                },
            )
        }
    }
}

/**
 * Sticky brand bar: Goza mark + "NativeLingo" wordmark left, 跟读/识物 segmented
 * switcher right. Floats over content (desktop `.topbar`).
 */
@Composable
private fun WorkbenchTopBar(
    modules: List<TopModule>,
    currentRoute: String?,
    showSwitcher: Boolean,
    onSelect: (TopModule) -> Unit,
) {
    val brand = LocalNativeLingoColors.current
    Row(
        Modifier
            .fillMaxWidth()
            .windowInsetsPadding(WindowInsets.statusBars)
            .padding(start = 14.dp, end = 14.dp, top = 10.dp, bottom = 6.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Image(
                painter = painterResource(R.drawable.goza_logo),
                contentDescription = null,  // decorative; the wordmark carries the name
                modifier = Modifier
                    .size(30.dp)
                    .clip(RoundedCornerShape(9.dp))
                    .shadow(elevation = 3.dp, shape = RoundedCornerShape(9.dp)),
            )
            Text(
                "NativeLingo",
                style = MaterialTheme.typography.titleLarge,
                color = brand.ink,
                modifier = Modifier.padding(start = 8.dp),
            )
        }

        if (showSwitcher) {
            ModuleSwitcher(modules, currentRoute, onSelect)
        }
    }
}

/** Segmented 跟读/识物 control — recessed track + ink-filled active pill. */
@Composable
private fun ModuleSwitcher(
    modules: List<TopModule>,
    currentRoute: String?,
    onSelect: (TopModule) -> Unit,
) {
    val brand = LocalNativeLingoColors.current
    Row(
        Modifier
            .background(brand.surfaceMuted, RoundedCornerShape(14.dp))
            .border(1.dp, brand.line, RoundedCornerShape(14.dp))
            .padding(2.dp),
        horizontalArrangement = Arrangement.spacedBy(3.dp),
    ) {
        modules.forEach { mod ->
            val active = currentRoute == mod.route
            val interaction = remember { MutableInteractionSource() }
            Text(
                text = mod.label,
                style = MaterialTheme.typography.titleSmall,
                color = if (active) brand.surface else brand.muted,
                modifier = Modifier
                    .clip(RoundedCornerShape(10.dp))
                    .background(if (active) brand.ink else Color.Transparent)
                    .clickable(interactionSource = interaction, indication = null) { onSelect(mod) }
                    .defaultMinSize(minWidth = 44.dp, minHeight = 44.dp)
                    .padding(horizontal = 14.dp),
            )
        }
    }
}
