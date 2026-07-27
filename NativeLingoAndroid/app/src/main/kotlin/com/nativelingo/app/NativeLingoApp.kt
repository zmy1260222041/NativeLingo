package com.nativelingo.app

import android.app.Application
import com.nativelingo.app.di.AppContainer

/**
 * Application entry point — constructs the [AppContainer] once so every screen
 * shares the single model registry / encoder / pipeline.
 */
class NativeLingoApp : Application() {

    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }
}
