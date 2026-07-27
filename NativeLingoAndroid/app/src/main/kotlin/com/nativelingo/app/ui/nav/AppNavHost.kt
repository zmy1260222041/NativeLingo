package com.nativelingo.app.ui.nav

import androidx.compose.runtime.Composable
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.nativelingo.app.di.AppContainer
import com.nativelingo.app.ui.practice.PracticeScreen
import com.nativelingo.app.ui.videolist.VideoListScreen

object Routes {
    const val VIDEOS = "videos"
    const val PRACTICE = "practice/{videoName}"
    fun practice(videoName: String) = "practice/$videoName"
}

@Composable
fun AppNavHost(container: AppContainer) {
    val nav = rememberNavController()
    NavHost(navController = nav, startDestination = Routes.VIDEOS) {
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
    }
}
