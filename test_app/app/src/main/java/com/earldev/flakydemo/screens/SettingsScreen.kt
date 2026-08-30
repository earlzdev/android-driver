package com.earldev.flakydemo.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.earldev.flakydemo.core.AppStore
import com.earldev.flakydemo.core.Settings
import com.earldev.flakydemo.core.logAction
import com.earldev.flakydemo.core.logScreen
import com.earldev.flakydemo.ui.AppTopBar
import com.earldev.flakydemo.ui.Banner
import com.earldev.flakydemo.ui.Divider12
import com.earldev.flakydemo.ui.PillButton
import com.earldev.flakydemo.ui.SectionLabel
import com.earldev.flakydemo.ui.driverTestTag
import com.earldev.flakydemo.ui.isLandscape
import kotlinx.coroutines.delay

private val SYNC_OPTIONS = listOf("Manual", "Hourly", "Daily")
private val REGIONS = listOf("Europe", "Americas", "Asia Pacific", "Africa")

/**
 * Screen 4 — settings.
 *
 * Bugs planted here: BUG-SET-01 (Save ignores the terms checkbox and no-ops), BUG-SET-02 (unsaved
 * edits and the confirmation banner vanish on rotation), BUG-SET-03 (one save in five is dropped
 * after saying "Saved"), BUG-SET-04 (cache slider is silently rounded to a multiple of 64),
 * BUG-SET-05 (the landscape Save discards the profile text fields), BUG-SET-06 (a 101–119 character bio
 * crashes the preview line).
 */
@Composable
fun SettingsScreen(onBack: () -> Unit) {
    // BUG-SET-02: the whole draft is a plain `remember` seeded from the store, so a rotation quietly
    // rolls every unsaved edit back to the last saved values without warning the user.
    var draft by remember { mutableStateOf(AppStore.settings) }
    var banner by remember { mutableStateOf<String?>(null) }
    var regionOpen by remember { mutableStateOf(false) }

    val landscape = isLandscape()

    LaunchedEffect(landscape) { logScreen("settings", "landscape=$landscape") }

    LaunchedEffect(banner) {
        if (banner != null) {
            delay(2500)
            banner = null
        }
    }

    /**
     * BUG-SET-05: the landscape pane got its own save path when the two-column layout was added,
     * and it rebuilds the payload from the *stored* profile fields instead of the draft. Toggles,
     * region and cache size are written; the display name, email and bio the user just typed are
     * silently discarded. In portrait the same edits save correctly.
     */
    fun saveFromLandscapePane() {
        if (!draft.acceptedTerms) {
            logAction("settings_save", "outcome=noop reason=terms_not_accepted pane=landscape")
            banner = "Saved"
            return
        }
        val stored = AppStore.settings
        val merged = draft.copy(
            displayName = stored.displayName,
            email = stored.email,
            bio = stored.bio,
            cacheMb = ((draft.cacheMb + 32) / 64) * 64,
        )
        AppStore.saveSettings(merged)
        banner = "Saved"
    }

    fun save() {
        // BUG-SET-01: the Save button is never disabled, and the guard that should have gated it
        // lives here — so saving without accepting the terms does nothing at all while still
        // reporting success to the user.
        if (!draft.acceptedTerms) {
            logAction("settings_save", "outcome=noop reason=terms_not_accepted")
            banner = "Saved"
            return
        }
        // BUG-SET-04: the slider reports whole megabytes but the store only keeps multiples of 64,
        // so 100 comes back as 128 the next time the screen is opened.
        val rounded = draft.copy(cacheMb = ((draft.cacheMb + 32) / 64) * 64)
        AppStore.saveSettings(rounded)
        banner = "Saved"
    }

    @Composable
    fun textFields(modifier: Modifier) {
        Column(modifier, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            SectionLabel("Profile", testTag = "label_profile")
            OutlinedTextField(
                value = draft.displayName,
                onValueChange = { draft = draft.copy(displayName = it) },
                label = { Text("Display name") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().driverTestTag("text_field_DisplayName"),
            )
            OutlinedTextField(
                value = draft.email,
                onValueChange = { draft = draft.copy(email = it) },
                label = { Text("Email") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().driverTestTag("text_field_Email"),
            )
            OutlinedTextField(
                value = draft.bio,
                onValueChange = { draft = draft.copy(bio = it) },
                label = { Text("Bio") },
                minLines = 3,
                modifier = Modifier.fillMaxWidth().driverTestTag("text_field_Bio"),
            )
            Text(
                // BUG-SET-06: the guard tests for 100 characters and the slice asks for 120, so any
                // bio between 101 and 119 characters long throws StringIndexOutOfBoundsException as
                // soon as it is typed.
                text = "Preview: " + if (draft.bio.length > 100) {
                    draft.bio.substring(0, 120) + "…"
                } else {
                    draft.bio
                },
                fontSize = 12.sp,
                modifier = Modifier.driverTestTag("bio_preview"),
            )
        }
    }

    @Composable
    fun toggles(modifier: Modifier) {
        Column(modifier, verticalArrangement = Arrangement.spacedBy(4.dp)) {
            SectionLabel("Preferences", testTag = "label_preferences")

            SwitchRow("Notifications", testTag = "switch_notifications", checked = draft.notifications) {
                draft = draft.copy(notifications = it)
            }
            SwitchRow("Dark mode", testTag = "switch_dark_mode", checked = draft.darkMode) {
                draft = draft.copy(darkMode = it)
            }
            SwitchRow("Usage analytics", testTag = "switch_analytics", checked = draft.analytics) {
                draft = draft.copy(analytics = it)
            }

            Divider12()
            SectionLabel("Sync frequency", testTag = "label_sync_frequency")
            SYNC_OPTIONS.forEach { option ->
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.driverTestTag("sync_option_row_$option"),
                ) {
                    RadioButton(
                        selected = draft.syncFrequency == option,
                        onClick = { draft = draft.copy(syncFrequency = option) },
                        modifier = Modifier.driverTestTag("radio_sync_$option"),
                    )
                    Text(option, modifier = Modifier.driverTestTag("radio_sync_label_$option"))
                }
            }

            Divider12()
            SectionLabel("Cache size", testTag = "label_cache_size")
            Text(
                text = "${draft.cacheMb} MB",
                modifier = Modifier.driverTestTag("cache_size_value"),
            )
            Slider(
                value = draft.cacheMb.toFloat(),
                onValueChange = { draft = draft.copy(cacheMb = it.toInt()) },
                // Continuous, so the value the user lands on is almost never a multiple of 64 —
                // which is what makes BUG-SET-04 visible the moment the screen is reopened.
                valueRange = 0f..1024f,
                modifier = Modifier.fillMaxWidth().driverTestTag("cache_size_slider"),
            )

            Divider12()
            SectionLabel("Region", testTag = "label_region")
            Box {
                PillButton(
                    label = "Region: ${draft.region}",
                    testTag = "region_dropdown_button",
                    onClick = { regionOpen = true },
                )
                DropdownMenu(
                    expanded = regionOpen,
                    onDismissRequest = { regionOpen = false },
                    modifier = Modifier.driverTestTag("region_dropdown_menu"),
                ) {
                    REGIONS.forEach { region ->
                        DropdownMenuItem(
                            text = { Text(region) },
                            onClick = {
                                draft = draft.copy(region = region)
                                regionOpen = false
                                logAction("settings_region", "region=$region")
                            },
                            modifier = Modifier.driverTestTag("region_option_${region.replace(' ', '_')}"),
                        )
                    }
                }
            }

            Divider12()
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(
                    checked = draft.acceptedTerms,
                    onCheckedChange = { draft = draft.copy(acceptedTerms = it) },
                    modifier = Modifier.driverTestTag("terms_checkbox"),
                )
                Text("I accept the terms", modifier = Modifier.driverTestTag("terms_label"))
            }
        }
    }

    @Composable
    fun actions(onSave: () -> Unit) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(vertical = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            PillButton(
                label = "Save",
                testTag = "save_button",
                selected = true,
                modifier = Modifier.weight(1f),
                onClick = onSave,
            )
            PillButton(
                label = "Reset",
                testTag = "reset_button",
                modifier = Modifier.weight(1f),
                onClick = {
                    draft = Settings()
                    banner = "Reset to defaults"
                    logAction("settings_reset")
                },
            )
        }
    }

    Column(Modifier.fillMaxSize().driverTestTag("settings_root")) {
        AppTopBar(title = "Settings", testTag = "settings_top_bar", onBack = onBack)

        banner?.let {
            Box(Modifier.padding(horizontal = 12.dp, vertical = 6.dp)) {
                Banner(text = it, testTag = "settings_banner", tone = Color(0xFF2E7D32))
            }
        }

        Text(
            text = "Stored: ${AppStore.settings.displayName} · ${AppStore.settings.cacheMb} MB · " +
                "sync ${AppStore.settings.syncFrequency}",
            fontSize = 12.sp,
            modifier = Modifier.padding(horizontal = 12.dp).driverTestTag("stored_summary"),
        )

        if (landscape) {
            Row(
                Modifier.weight(1f).fillMaxWidth().padding(12.dp),
                horizontalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                Column(
                    Modifier
                        .weight(1f)
                        .fillMaxHeight()
                        .verticalScroll(rememberScrollState()),
                ) {
                    textFields(Modifier.fillMaxWidth())
                }
                Column(
                    Modifier
                        .weight(1f)
                        .fillMaxHeight()
                        .background(MaterialTheme.colorScheme.surfaceVariant)
                        .padding(8.dp),
                ) {
                    toggles(Modifier.fillMaxWidth())
                    Spacer(Modifier.height(8.dp))
                    actions(onSave = { saveFromLandscapePane() })
                }
            }
        } else {
            Column(
                Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState())
                    .padding(12.dp),
            ) {
                textFields(Modifier.fillMaxWidth())
                toggles(Modifier.fillMaxWidth())
                actions(onSave = { save() })
            }
        }
    }
}

@Composable
private fun SwitchRow(label: String, testTag: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().driverTestTag("${testTag}_row"),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, modifier = Modifier.weight(1f).driverTestTag("${testTag}_label"))
        Switch(checked = checked, onCheckedChange = onChange, modifier = Modifier.driverTestTag(testTag))
    }
}
