package com.earldev.flakydemo.core

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

data class Settings(
    val displayName: String = "Demo User",
    val email: String = "demo@test.dev",
    val bio: String = "",
    val notifications: Boolean = true,
    val darkMode: Boolean = false,
    val analytics: Boolean = false,
    val syncFrequency: String = "Hourly",
    val cacheMb: Int = 256,
    val region: String = "Europe",
    val acceptedTerms: Boolean = false,
)

/**
 * Process-wide state. Deliberately a singleton rather than a ViewModel: it survives rotation, so
 * anything that *does* get lost on a rotation is lost because the screen holds it in the wrong kind
 * of remember, not because the store dropped it.
 */
object AppStore {

    /**
     * A process-level scope, the way a repository or a ViewModel would own one. Work launched here
     * keeps running after the screen that started it has left composition — which is exactly what
     * makes BUG-LOG-03 observable instead of quietly cancelled.
     */
    val appScope = CoroutineScope(Dispatchers.Main.immediate + SupervisorJob())

    var signedInEmail by mutableStateOf<String?>(null)

    /** Bumped by the dashboard's counter; deliberately not read back by anything else. */
    var lifetimeTaps by mutableStateOf(0)

    var settings by mutableStateOf(Settings())
        private set

    /** How many times [saveSettings] silently dropped a write — the dashboard surfaces it. */
    var droppedWrites by mutableStateOf(0)
        private set

    val catalog = mutableStateListOf<Item>().also { it.addAll(buildCatalog()) }

    var lastDeletedName by mutableStateOf<String?>(null)

    fun reset() {
        signedInEmail = null
        lifetimeTaps = 0
        settings = Settings()
        droppedWrites = 0
        catalog.clear()
        catalog.addAll(buildCatalog())
        lastDeletedName = null
    }

    /**
     * BUG-SET-03: about one write in five is acknowledged and then thrown away. The caller still
     * shows its "Saved" snackbar, so the only way to notice is to leave the screen and come back.
     */
    fun saveSettings(next: Settings): Boolean {
        if (Flake.hit(0.2, "settings_save_dropped")) {
            droppedWrites++
            logAction("settings_save", "acknowledged=true persisted=false dropped=$droppedWrites")
            return true
        }
        settings = next
        logAction("settings_save", "acknowledged=true persisted=true")
        return true
    }

    fun itemById(id: Int): Item? = catalog.firstOrNull { it.id == id }
}
