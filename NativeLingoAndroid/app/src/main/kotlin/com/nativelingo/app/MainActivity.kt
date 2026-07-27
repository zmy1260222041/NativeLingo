package com.nativelingo.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.nativelingo.app.ui.nav.AppNavHost
import com.nativelingo.app.ui.theme.NativeLingoTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val container = (application as NativeLingoApp).container
        setContent {
            NativeLingoTheme {
                AppNavHost(container)
            }
        }
    }
}
