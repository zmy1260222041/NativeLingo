package com.nativelingo.app.ui.nav

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.nativelingo.app.di.AppContainer
import com.nativelingo.app.ui.memorize.MemorizeScreen
import com.nativelingo.app.ui.practice.PracticeScreen
import com.nativelingo.app.ui.videolist.VideoListScreen

object Routes {
    const val VIDEOS = "videos"
    const val PRACTICE = "practice/{videoName}"
    fun practice(videoName: String) = "practice/$videoName"

    /** Top-level Memorizing (识物) destination — FR-13. */
    const val MEMORIZE = "memorize"
}

/** The two top-level modules, mirroring the desktop workbench's 跟读 / 识物 tabs.
 *  Practice is a child of 跟读 (a picked video), so it hides the bottom bar. */
private data class TopModule(val route: String, val label: String, val icon: ImageVector)

private val TOP_MODULES = listOf(
    // Core icons only (no material-icons-extended dep): a play arrow for the
    // shadowing practice track, a magnifier for the recognition track.
    TopModule(Routes.VIDEOS, "跟读", Icons.Filled.PlayArrow),
    TopModule(Routes.MEMORIZE, "识物", Icons.Filled.Search),
)

@Composable
fun AppNavHost(container: AppContainer) {
    val nav = rememberNavController()
    val backStack by nav.currentBackStackEntryAsState()
    val currentRoute = backStack?.destination?.route
    // The bottom bar belongs on top-level destinations only — practice is a drill-in.
    val showBottomBar = currentRoute in TOP_MODULES.map { it.route }

    Scaffold(
        bottomBar = {
            if (showBottomBar) {
                NavigationBar {
                    TOP_MODULES.forEach { mod ->
                        NavigationBarItem(
                            selected = currentRoute == mod.route,
                            onClick = {
                                // Pop to the start destination before adding, to avoid
                                // a growing back stack of tab switches.
                                if (currentRoute != mod.route) {
                                    nav.navigate(mod.route) {
                                        popUpTo(nav.graph.startDestinationId) { saveState = true }
                                        launchSingleTop = true
                                        restoreState = true
                                    }
                                }
                            },
                            icon = { Icon(mod.icon, contentDescription = mod.label) },
                            label = { Text(mod.label) },
                        )
                    }
                }
            }
        },
    ) { pad ->
        NavHost(
            navController = nav,
            startDestination = Routes.VIDEOS,
            modifier = Modifier.padding(pad),
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
    }
}
