package com.earldev.flakydemo

import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.semantics.semantics
import com.earldev.flakydemo.core.AppStore
import com.earldev.flakydemo.core.Flake
import com.earldev.flakydemo.core.TAG
import com.earldev.flakydemo.core.logScreen
import com.earldev.flakydemo.screens.CatalogScreen
import com.earldev.flakydemo.screens.DashboardScreen
import com.earldev.flakydemo.screens.DetailScreen
import com.earldev.flakydemo.screens.LoginScreen
import com.earldev.flakydemo.screens.SettingsScreen
import com.earldev.flakydemo.ui.theme.FlakyDemoTheme

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Launch knobs, so a flaky failure can be pinned down instead of chased:
        //   adb shell am start -n com.earldev.flakydemo/.MainActivity --el flake_seed 42
        //   adb shell am start -n com.earldev.flakydemo/.MainActivity --ez flake_enabled false
        if (savedInstanceState == null) {
            val seed = intent?.getLongExtra("flake_seed", -1L) ?: -1L
            val enabled = intent?.getBooleanExtra("flake_enabled", true) ?: true
            Flake.init(if (seed >= 0) seed else System.nanoTime(), enabled)
            if (intent?.getBooleanExtra("reset_store", false) == true) AppStore.reset()
        }
        Log.i(TAG, "activity onCreate recreated=${savedInstanceState != null} seed=${Flake.seed}")

        enableEdgeToEdge()
        setContent {
            FlakyDemoTheme(darkTheme = AppStore.settings.darkMode) {
                AppRoot()
            }
        }
    }
}

private const val LOGIN = "login"
private const val DASHBOARD = "dashboard"
private const val CATALOG = "catalog"
private const val SETTINGS = "settings"

@Composable
fun AppRoot() {
    // The back stack lives in a single saveable String ("login|dashboard|detail/12") so navigation
    // itself survives rotation. Anything a screen loses on rotation is the screen's own doing.
    var stack by rememberSaveable { mutableStateOf(LOGIN) }
    val routes = stack.split("|")
    val current = routes.last()

    fun navigate(route: String) {
        stack = "$stack|$route"
        logScreen(route, "stack=$stack")
    }

    fun replace(route: String) {
        stack = route
        logScreen(route, "stack=$stack")
    }

    fun pop() {
        if (routes.size > 1) {
            stack = routes.dropLast(1).joinToString("|")
            logScreen(routes[routes.size - 2], "stack=$stack popped")
        }
    }

    BackHandler(enabled = routes.size > 1) { pop() }

    Scaffold(
        modifier = Modifier
            .fillMaxSize()
            .semantics { testTagsAsResourceId = true },
    ) { innerPadding ->
        Box(Modifier.padding(innerPadding)) {
            when {
                current == LOGIN -> LoginScreen(
                    onSignedIn = { navigate(DASHBOARD) },
                )

                current == DASHBOARD -> DashboardScreen(
                    onOpenCatalog = { navigate(CATALOG) },
                    onOpenSettings = { navigate(SETTINGS) },
                    onOpenItem = { id -> navigate("detail/$id") },
                    onSignOut = { replace(LOGIN) },
                )

                current == CATALOG -> CatalogScreen(
                    onBack = { pop() },
                    onOpenItem = { id -> navigate("detail/$id") },
                )

                current == SETTINGS -> SettingsScreen(
                    onBack = { pop() },
                )

                current.startsWith("detail/") -> DetailScreen(
                    itemId = current.removePrefix("detail/").toIntOrNull() ?: 1,
                    onBack = { pop() },
                )
            }
        }
    }
}
