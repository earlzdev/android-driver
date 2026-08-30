package com.earldev.flakydemo.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.earldev.flakydemo.core.AppStore
import com.earldev.flakydemo.core.Flake
import com.earldev.flakydemo.core.logAction
import com.earldev.flakydemo.core.logScreen
import com.earldev.flakydemo.ui.Banner
import com.earldev.flakydemo.ui.PillButton
import com.earldev.flakydemo.ui.driverTestTag
import com.earldev.flakydemo.ui.isLandscape
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Screen 1 — sign in.
 *
 * Bugs planted here: BUG-LOG-01 (random network failure), BUG-LOG-02 (email lost on rotation),
 * BUG-LOG-03 (no in-flight guard, so a double tap signs in twice), BUG-LOG-04 (wrong error copy for
 * an untrimmed email), BUG-LOG-05 (guest button missing in landscape).
 */
@Composable
fun LoginScreen(onSignedIn: () -> Unit) {
    // BUG-LOG-02: `remember`, not `rememberSaveable`. The password below is saved correctly, so a
    // rotation mid-form empties exactly one of the two fields.
    var email by remember { mutableStateOf("") }
    var password by rememberSaveable { mutableStateOf("") }

    var rememberMe by rememberSaveable { mutableStateOf(false) }
    var showPassword by rememberSaveable { mutableStateOf(false) }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var attempts by rememberSaveable { mutableIntStateOf(0) }
    val inFlight = remember { mutableIntStateOf(0) }

    val landscape = isLandscape()

    fun submit() {
        // BUG-LOG-03: nothing checks `loading` here and the button stays enabled while a request is
        // in flight, so a second tap starts a second coroutine. Both call onSignedIn(), which pushes
        // the dashboard onto the stack twice — Back from the dashboard lands on the dashboard again.
        inFlight.intValue += 1
        attempts += 1
        loading = true
        error = null
        logAction("login_submit", "attempt=$attempts inFlight=${inFlight.intValue} email=$email")
        // Launched on the process-level scope, not the composition's — see BUG-LOG-03.
        AppStore.appScope.launch {
            delay(Flake.jitter(500, 900))
            inFlight.intValue -= 1
            loading = false
            when {
                // BUG-LOG-01: roughly one attempt in three fails for no reason. A retry usually works.
                Flake.hit(0.3, "login_network_error") -> {
                    error = "Network unavailable. Check your connection."
                    logAction("login_result", "outcome=network_error")
                }
                // BUG-LOG-04: the email is validated untrimmed, but the failure is reported as a
                // password problem — so " demo@test.dev" reads as a wrong password.
                !email.contains("@") || email != email.trim() -> {
                    error = "Password is incorrect."
                    logAction("login_result", "outcome=rejected reason=email_shape")
                }

                password.length < 6 -> {
                    error = "Password is incorrect."
                    logAction("login_result", "outcome=rejected reason=password_length")
                }

                else -> {
                    AppStore.signedInEmail = email.trim()
                    logAction("login_result", "outcome=success email=${email.trim()}")
                    onSignedIn()
                }
            }
        }
    }

    LaunchedEffect(landscape) { logScreen("login", "landscape=$landscape") }

    @Composable
    fun form(modifier: Modifier) {
        Column(
            modifier = modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = "Sign in",
                fontSize = 26.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.driverTestTag("login_heading"),
            )

            error?.let {
                Banner(text = it, testTag = "login_error_banner", tone = Color(0xFFB3261E))
            }

            OutlinedTextField(
                value = email,
                onValueChange = { email = it },
                label = { Text("Email") },
                singleLine = true,
                modifier = Modifier
                    .fillMaxWidth()
                    .driverTestTag("text_field_Email"),
            )

            OutlinedTextField(
                value = password,
                onValueChange = { password = it },
                label = { Text("Password") },
                singleLine = true,
                visualTransformation =
                    if (showPassword) VisualTransformation.None else PasswordVisualTransformation(),
                modifier = Modifier
                    .fillMaxWidth()
                    .driverTestTag("text_field_Password"),
            )

            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(
                    checked = rememberMe,
                    onCheckedChange = { rememberMe = it },
                    modifier = Modifier.driverTestTag("remember_me_checkbox"),
                )
                Text("Remember me", modifier = Modifier.driverTestTag("remember_me_label"))
                Spacer(Modifier.weight(1f))
                Text("Show", modifier = Modifier.driverTestTag("show_password_label"))
                Switch(
                    checked = showPassword,
                    onCheckedChange = { showPassword = it },
                    modifier = Modifier.driverTestTag("show_password_switch"),
                )
            }

            // The spinner sits beside the button rather than replacing it, and the button is never
            // disabled — which is what lets BUG-LOG-03 fire on a double tap.
            Row(
                modifier = Modifier.fillMaxWidth().height(56.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                PillButton(
                    label = "Sign in",
                    testTag = "login_button",
                    selected = true,
                    modifier = Modifier.weight(1f),
                    onClick = { submit() },
                )
                if (loading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(28.dp).driverTestTag("login_progress"),
                    )
                }
            }

            Text(
                text = "Attempts this session: $attempts",
                fontSize = 12.sp,
                modifier = Modifier.driverTestTag("login_attempt_counter"),
            )

            // BUG-LOG-05: when the two-pane landscape layout was added, the guest entry point was
            // left behind in the portrait branch. In landscape it is not rendered at all, so it is
            // absent from the hierarchy rather than merely off-screen, and the whole guest flow is
            // unreachable until the device is rotated back.
            if (!landscape) {
                PillButton(
                    label = "Continue as guest",
                    testTag = "guest_button",
                    modifier = Modifier.fillMaxWidth(),
                    onClick = {
                        AppStore.signedInEmail = "guest@local"
                        logAction("login_result", "outcome=guest")
                        onSignedIn()
                    },
                )
            }

            Text(
                text = "FlakyDemo build 1.0 · seed ${Flake.seed}",
                fontSize = 11.sp,
                modifier = Modifier.driverTestTag("login_footer"),
            )
        }
    }

    if (landscape) {
        Row(Modifier.fillMaxSize().driverTestTag("login_root_landscape")) {
            Column(
                modifier = Modifier
                    .weight(0.4f)
                    .fillMaxHeight()
                    .background(MaterialTheme.colorScheme.secondaryContainer)
                    .padding(20.dp),
                verticalArrangement = Arrangement.Center,
            ) {
                Text(
                    text = "FlakyDemo",
                    fontSize = 30.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.driverTestTag("brand_title"),
                )
                Text(
                    text = "A deliberately unreliable test fixture.",
                    modifier = Modifier.driverTestTag("brand_subtitle"),
                )
            }
            form(
                Modifier
                    .weight(0.6f)
                    .fillMaxHeight()
                    .verticalScroll(rememberScrollState()),
            )
        }
    } else {
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .driverTestTag("login_root_portrait"),
        ) {
            Text(
                text = "FlakyDemo",
                fontSize = 30.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(start = 16.dp, top = 24.dp).driverTestTag("brand_title"),
            )
            form(Modifier.fillMaxWidth())
        }
    }
}
