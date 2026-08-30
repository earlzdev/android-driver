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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.earldev.flakydemo.core.AppStore
import com.earldev.flakydemo.core.Flake
import com.earldev.flakydemo.core.logAction
import com.earldev.flakydemo.core.logScreen
import com.earldev.flakydemo.ui.AppTopBar
import com.earldev.flakydemo.ui.PillButton
import com.earldev.flakydemo.ui.SectionLabel
import com.earldev.flakydemo.ui.StatCard
import com.earldev.flakydemo.ui.driverTestTag
import com.earldev.flakydemo.ui.isLandscape
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private val PERIODS = listOf("Today", "Week", "Month", "Year")

data class Stats(val orders: Int, val revenueCents: Int, val errors: Int, val uptime: String)

/** Fixed numbers per period, so a test can assert an exact string rather than "something changed". */
fun statsFor(period: String): Stats = when (period) {
    "Today" -> Stats(42, 1284_00, 3, "99.1%")
    "Week" -> Stats(310, 9640_00, 11, "98.7%")
    "Month" -> Stats(1288, 41250_00, 47, "99.4%")
    else -> Stats(15402, 502180_00, 512, "99.9%")
}

private fun money(cents: Int): String {
    val units = cents / 100
    val grouped = units.toString().reversed().chunked(3).joinToString(",").reversed()
    return "$" + grouped + "." + (cents % 100).toString().padStart(2, '0')
}

/**
 * Screen 2 — dashboard.
 *
 * Bugs planted here: BUG-DSH-01 (refresh serves the previous period's numbers), BUG-DSH-02 (period
 * and counter reset on rotation), BUG-DSH-03 (sync bar stalls at 90%), BUG-DSH-04 (Errors and Uptime
 * values transposed in landscape), BUG-DSH-05 (three fast refreshes divide by zero).
 */
@Composable
fun DashboardScreen(
    onOpenCatalog: () -> Unit,
    onOpenSettings: () -> Unit,
    onOpenItem: (Int) -> Unit,
    onSignOut: () -> Unit,
) {
    // BUG-DSH-02: both of these are plain `remember`, so a rotation snaps the period back to Today
    // and throws the counter away. The store behind them survives rotation perfectly well.
    var period by remember { mutableStateOf(PERIODS.first()) }
    var counter by remember { mutableIntStateOf(0) }

    var stats by remember { mutableStateOf(statsFor(PERIODS.first())) }
    var servedPeriod by remember { mutableStateOf(PERIODS.first()) }
    var refreshing by remember { mutableStateOf(false) }
    var syncId by remember { mutableIntStateOf(0) }
    var syncing by remember { mutableStateOf(false) }
    val syncProgress = remember { mutableFloatStateOf(0f) }
    val refreshTimes = remember { mutableStateListOf<Long>() }
    var avgPerDay by remember { mutableIntStateOf(6) }

    val scope = rememberCoroutineScope()
    val landscape = isLandscape()

    LaunchedEffect(landscape) { logScreen("dashboard", "landscape=$landscape period=$period") }

    fun refresh() {
        val now = System.currentTimeMillis()
        refreshTimes.removeAll { now - it > 2000 }
        refreshTimes.add(now)

        val requested = period
        refreshing = true
        logAction("dashboard_refresh", "period=$requested burst=${refreshTimes.size}")
        scope.launch {
            delay(Flake.jitter(350, 650))
            // BUG-DSH-01: about one refresh in four re-serves whatever period was rendered last
            // instead of the one that is selected, and the header still names the selected period.
            val serve = if (Flake.hit(0.25, "dashboard_stale_stats")) servedPeriod else requested
            stats = statsFor(serve)
            servedPeriod = requested
            refreshing = false
            logAction("dashboard_refresh_done", "requested=$requested served=$serve")

            // BUG-DSH-05: the divisor is the number of refreshes left over after subtracting the
            // three that a burst is allowed, so exactly three refreshes inside two seconds is a
            // division by zero and an uncaught ArithmeticException.
            if (refreshTimes.size >= 3) {
                avgPerDay = stats.orders / (refreshTimes.size - 3)
                logAction("dashboard_avg", "avg=$avgPerDay")
            }
        }
    }

    fun startSync() {
        syncId += 1
        syncing = true
    }

    LaunchedEffect(syncId) {
        if (syncId == 0) return@LaunchedEffect
        syncProgress.floatValue = 0f
        // BUG-DSH-03: one sync in five stops updating at 90% and never clears `syncing`, so the bar
        // stays on screen forever and an `expect_gone` on it hangs to its timeout.
        val stall = Flake.hit(0.2, "dashboard_sync_stall")
        while (syncProgress.floatValue < 1f) {
            delay(140)
            syncProgress.floatValue = (syncProgress.floatValue + 0.1f).coerceAtMost(1f)
            if (stall && syncProgress.floatValue >= 0.9f) {
                logAction("dashboard_sync", "outcome=stalled at=0.9")
                return@LaunchedEffect
            }
        }
        syncing = false
        logAction("dashboard_sync", "outcome=complete")
    }

    @Composable
    fun periodChips() {
        LazyRow(
            modifier = Modifier.fillMaxWidth().driverTestTag("period_chip_row"),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            PERIODS.forEach { p ->
                item(key = p) {
                    PillButton(
                        label = p,
                        testTag = "period_chip_$p",
                        selected = period == p,
                        onClick = {
                            period = p
                            logAction("dashboard_period", "period=$p")
                            refresh()
                        },
                    )
                }
            }
        }
    }

    @Composable
    fun statCards(modifier: Modifier) {
        // BUG-DSH-04: the landscape row is a copy of the portrait one with the last two values
        // transposed — the Errors card shows the uptime percentage and the Uptime card shows the
        // error count. Both cards are present and both labels are correct, so only an assertion on
        // the values catches it, and only in landscape.
        if (landscape) {
            Row(modifier, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                StatCard("Orders", stats.orders.toString(), testTag = "stat_orders", modifier = Modifier.weight(1f))
                StatCard("Revenue", money(stats.revenueCents), testTag = "stat_revenue", modifier = Modifier.weight(1f))
                StatCard("Errors", stats.uptime, testTag = "stat_errors", modifier = Modifier.weight(1f))
                StatCard("Uptime", stats.errors.toString(), testTag = "stat_uptime", modifier = Modifier.weight(1f))
            }
        } else {
            Column(modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    StatCard("Orders", stats.orders.toString(), testTag = "stat_orders", modifier = Modifier.weight(1f))
                    StatCard("Revenue", money(stats.revenueCents), testTag = "stat_revenue", modifier = Modifier.weight(1f))
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    StatCard("Errors", stats.errors.toString(), testTag = "stat_errors", modifier = Modifier.weight(1f))
                    StatCard("Uptime", stats.uptime, testTag = "stat_uptime", modifier = Modifier.weight(1f))
                }
            }
        }
    }

    @Composable
    fun body(modifier: Modifier) {
        Column(
            modifier = modifier
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = "Signed in as ${AppStore.signedInEmail ?: "unknown"}",
                modifier = Modifier.driverTestTag("dashboard_greeting"),
            )

            SectionLabel("Period", testTag = "label_period")
            periodChips()

            Text(
                text = "Showing: $period",
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.driverTestTag("period_readout"),
            )

            statCards(Modifier.fillMaxWidth())

            Text(
                text = "Average per day: $avgPerDay",
                fontSize = 12.sp,
                modifier = Modifier.driverTestTag("avg_per_day"),
            )

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                PillButton("Refresh", testTag = "refresh_button", onClick = { refresh() })
                PillButton("Sync now", testTag = "sync_button", onClick = { startSync() })
            }

            if (refreshing) {
                Text("Refreshing…", modifier = Modifier.driverTestTag("refresh_progress"))
            }

            if (syncing) {
                Column(Modifier.fillMaxWidth().driverTestTag("sync_block")) {
                    Text(
                        text = "Sync ${(syncProgress.floatValue * 100).toInt()}%",
                        modifier = Modifier.driverTestTag("sync_percent"),
                    )
                    LinearProgressIndicator(
                        progress = { syncProgress.floatValue },
                        modifier = Modifier.fillMaxWidth().driverTestTag("sync_progress_bar"),
                    )
                }
            }


            SectionLabel("Session counter", testTag = "label_counter")
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                PillButton("-", testTag = "counter_minus", onClick = {
                    counter -= 1
                    AppStore.lifetimeTaps += 1
                })
                Text(
                    text = counter.toString(),
                    fontSize = 24.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.driverTestTag("counter_value"),
                )
                PillButton("+", testTag = "counter_plus", onClick = {
                    counter += 1
                    AppStore.lifetimeTaps += 1
                })
                Text(
                    text = "lifetime ${AppStore.lifetimeTaps}",
                    fontSize = 12.sp,
                    modifier = Modifier.driverTestTag("lifetime_taps"),
                )
            }

            SectionLabel("Go to", testTag = "label_navigation")
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                PillButton(
                    "Open catalog",
                    testTag = "nav_catalog_button",
                    modifier = Modifier.fillMaxWidth(),
                    onClick = onOpenCatalog,
                )
                PillButton(
                    "Open settings",
                    testTag = "nav_settings_button",
                    modifier = Modifier.fillMaxWidth(),
                    onClick = onOpenSettings,
                )
                PillButton(
                    "Open featured item",
                    testTag = "featured_item_button",
                    modifier = Modifier.fillMaxWidth(),
                    onClick = { onOpenItem(13) },
                )
            }

            Text(
                text = "Dropped writes: ${AppStore.droppedWrites}",
                fontSize = 12.sp,
                modifier = Modifier.driverTestTag("dropped_writes"),
            )

            PillButton(
                "Sign out",
                testTag = "logout_button",
                modifier = Modifier.fillMaxWidth(),
                onClick = {
                    AppStore.signedInEmail = null
                    logAction("logout")
                    onSignOut()
                },
            )
        }
    }

    Column(Modifier.fillMaxSize().driverTestTag("dashboard_root")) {
        AppTopBar(title = "Dashboard", testTag = "dashboard_top_bar") {
            Text(
                text = if (landscape) "landscape" else "portrait",
                fontSize = 12.sp,
                modifier = Modifier.driverTestTag("orientation_readout"),
            )
        }
        if (landscape) {
            Row(Modifier.weight(1f).fillMaxWidth()) {
                body(Modifier.weight(1f).fillMaxHeight())
                Column(
                    modifier = Modifier
                        .width(420.dp)
                        .fillMaxHeight()
                        .background(MaterialTheme.colorScheme.surfaceVariant)
                        .padding(12.dp)
                        .driverTestTag("activity_panel"),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    Text(
                        text = "Recent activity",
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.driverTestTag("activity_panel_title"),
                    )
                    for (i in 1..6) {
                        Text(
                            text = "Order #${1000 + i} · ${money(1200 * i)}",
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                            modifier = Modifier.driverTestTag("activity_row_$i"),
                        )
                    }
                    Spacer(Modifier.height(8.dp))
                    Box(Modifier.fillMaxWidth().height(1.dp).background(MaterialTheme.colorScheme.outline))
                }
            }
        } else {
            body(Modifier.weight(1f).fillMaxWidth())
        }
    }
}
