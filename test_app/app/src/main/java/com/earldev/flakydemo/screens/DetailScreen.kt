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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.earldev.flakydemo.core.AppStore
import com.earldev.flakydemo.core.Flake
import com.earldev.flakydemo.core.formatPrice
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

private val PORTRAIT_TABS = listOf("Overview", "Specs", "Reviews")
private val LANDSCAPE_TABS = listOf("Gallery", "Overview", "Specs", "Reviews")

/**
 * Screen 5 — item detail.
 *
 * Bugs planted here: BUG-DET-01 (a rotation hides the delete dialog but keeps the pending
 * confirmation armed), BUG-DET-02 (delete sometimes removes the neighbouring row), BUG-DET-03 (tab
 * resets on rotation), BUG-DET-04 (Reviews crashes for an item with no reviews), BUG-DET-05 (total
 * lags the quantity by one step), BUG-DET-06 (landscape tabs are off by one).
 */
@Composable
fun DetailScreen(itemId: Int, onBack: () -> Unit) {
    val item = AppStore.itemById(itemId)
    val landscape = isLandscape()

    if (item == null) {
        Column(Modifier.fillMaxSize().driverTestTag("detail_root")) {
            AppTopBar(title = "Not found", testTag = "detail_top_bar", onBack = onBack)
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text(
                    "Item $itemId is gone.",
                    modifier = Modifier.driverTestTag("detail_missing_message"),
                )
            }
        }
        return
    }

    // BUG-DET-03: the selected tab is a plain `remember`, so every rotation snaps back to the first
    // tab, while the quantity right below it is saved correctly.
    var tab by remember { mutableIntStateOf(0) }
    var qty by rememberSaveable { mutableIntStateOf(1) }
    var total by remember { mutableIntStateOf(item.price) }
    var rating by rememberSaveable { mutableIntStateOf(0) }
    var specsExpanded by remember { mutableStateOf(false) }
    var loading by remember { mutableStateOf(true) }
    var banner by remember { mutableStateOf<String?>(null) }

    // BUG-DET-01: the dialog's visibility is forgotten across a rotation but the armed confirmation
    // is not, so the dialog disappears and the *next* primary action on the screen — Add to cart,
    // Share — silently consumes the pending delete instead.
    var confirmVisible by remember { mutableStateOf(false) }
    var pendingDelete by rememberSaveable { mutableStateOf(false) }

    LaunchedEffect(itemId) {
        loading = true
        logScreen("detail", "item=$itemId reviews=${item.reviews.size} landscape=$landscape")
        delay(Flake.jitter(250, 500))
        loading = false
    }

    LaunchedEffect(banner) {
        if (banner != null) {
            delay(2500)
            banner = null
        }
    }

    fun performDelete() {
        val index = AppStore.catalog.indexOfFirst { it.id == item.id }
        if (index < 0) return
        // BUG-DET-02: about one delete in four resolves the victim by the position the row held
        // before the catalog was last re-sorted, which is the row after the one the user opened.
        val victimIndex = if (Flake.hit(0.25, "detail_delete_off_by_one")) {
            (index + 1).coerceAtMost(AppStore.catalog.size - 1)
        } else {
            index
        }
        val victim = AppStore.catalog[victimIndex]
        AppStore.lastDeletedName = victim.name
        AppStore.catalog.removeAt(victimIndex)
        logAction("detail_delete", "requested=${item.id} deleted=${victim.id} name=${victim.name}")
        onBack()
    }

    /** Every primary action funnels through here, which is where the pending confirmation leaks. */
    fun primaryAction(name: String, body: () -> Unit) {
        if (pendingDelete) {
            pendingDelete = false
            logAction("detail_pending_consumed", "by=$name")
            performDelete()
            return
        }
        body()
    }

    @Composable
    fun overview() {
        Column(
            Modifier.fillMaxWidth().driverTestTag("tab_content_overview"),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            SectionLabel("Overview", testTag = "label_overview")
            Text(item.name, fontSize = 20.sp, fontWeight = FontWeight.Bold, modifier = Modifier.driverTestTag("detail_name"))
            Text("Category: ${item.category}", modifier = Modifier.driverTestTag("detail_category"))
            Text("Unit price: ${formatPrice(item.price)}", modifier = Modifier.driverTestTag("detail_unit_price"))
            Text(
                text = if (item.inStock) "In stock" else "Backorder",
                modifier = Modifier.driverTestTag("detail_stock"),
            )
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(120.dp)
                    .background(MaterialTheme.colorScheme.secondaryContainer)
                    .driverTestTag("detail_hero_image"),
                contentAlignment = Alignment.Center,
            ) {
                Text("image placeholder", modifier = Modifier.driverTestTag("hero_placeholder_label"))
            }
        }
    }

    @Composable
    fun specs() {
        Column(
            Modifier.fillMaxWidth().driverTestTag("tab_content_specs"),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            SectionLabel("Specifications", testTag = "label_specs")
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { specsExpanded = !specsExpanded }
                    .padding(vertical = 8.dp)
                    .driverTestTag("specs_expander"),
            ) {
                Text(
                    text = if (specsExpanded) "Hide details" else "Show details",
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.driverTestTag("specs_expander_label"),
                )
            }
            if (specsExpanded) {
                Column(Modifier.driverTestTag("specs_expanded_block")) {
                    Text("SKU: FD-${item.id.toString().padStart(4, '0')}", modifier = Modifier.driverTestTag("spec_sku"))
                    Text("Weight: ${900 + item.id * 7} g", modifier = Modifier.driverTestTag("spec_weight"))
                    Text("Warranty: ${(item.id % 3) + 1} years", modifier = Modifier.driverTestTag("spec_warranty"))
                    Text("Origin: ${item.category} line", modifier = Modifier.driverTestTag("spec_origin"))
                }
            }
            Divider12()
            SectionLabel("Your rating", testTag = "label_rating")
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                (1..5).forEach { star ->
                    PillButton(
                        label = if (star <= rating) "*" else "-",
                        testTag = "rating_star_$star",
                        selected = star <= rating,
                        onClick = {
                            rating = star
                            logAction("detail_rating", "item=${item.id} stars=$star")
                        },
                    )
                }
                Text("$rating/5", modifier = Modifier.driverTestTag("rating_value"))
            }
        }
    }

    @Composable
    fun reviews() {
        Column(
            Modifier.fillMaxWidth().driverTestTag("tab_content_reviews"),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            SectionLabel("Reviews (${item.reviews.size})", testTag = "label_reviews")
            // BUG-DET-04: nothing checks for an empty list. Items 13 and 42 ship without reviews, so
            // opening this tab on either of them throws NoSuchElementException.
            val top = item.reviews.first()
            Card(Modifier.fillMaxWidth().driverTestTag("top_review_card")) {
                Column(Modifier.padding(12.dp)) {
                    Text("Top review", fontWeight = FontWeight.Bold, modifier = Modifier.driverTestTag("top_review_title"))
                    Text("${top.stars}/5 by ${top.author}", modifier = Modifier.driverTestTag("top_review_meta"))
                    Text(top.body, modifier = Modifier.driverTestTag("top_review_body"))
                }
            }
            item.reviews.forEachIndexed { i, review ->
                Text(
                    text = "${review.stars}/5 — ${review.body}",
                    fontSize = 13.sp,
                    modifier = Modifier.driverTestTag("review_row_$i"),
                )
            }
        }
    }

    @Composable
    fun tabContent() {
        // BUG-DET-06: landscape prepends a Gallery tab but the dispatch below still uses the
        // portrait indices, so in landscape every tab renders the content of the tab after it.
        when (tab) {
            0 -> overview()
            1 -> specs()
            else -> reviews()
        }
    }

    @Composable
    fun body(modifier: Modifier) {
        Column(
            modifier = modifier.verticalScroll(rememberScrollState()).padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            if (loading) {
                LinearProgressIndicator(
                    progress = { 0.4f },
                    modifier = Modifier.fillMaxWidth().driverTestTag("detail_progress"),
                )
            }

            banner?.let { Banner(text = it, testTag = "detail_banner", tone = Color(0xFF2E7D32)) }

            if (pendingDelete && !confirmVisible) {
                Banner(
                    text = "Delete confirmation is still armed.",
                    testTag = "pending_delete_banner",
                    tone = Color(0xFFB3261E),
                )
            }

            val tabs = if (landscape) LANDSCAPE_TABS else PORTRAIT_TABS
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                tabs.forEachIndexed { index, name ->
                    PillButton(
                        label = name,
                        testTag = "tab_$name",
                        selected = tab == index,
                        onClick = {
                            tab = index
                            logAction("detail_tab", "index=$index name=$name")
                        },
                    )
                }
            }

            tabContent()

            Divider12()
            SectionLabel("Quantity", testTag = "label_quantity")
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                PillButton("-", testTag = "qty_minus", onClick = {
                    val before = qty
                    qty = (qty - 1).coerceAtLeast(1)
                    total = if (Flake.hit(0.3, "detail_total_stale")) item.price * before else item.price * qty
                })
                Text(
                    text = qty.toString(),
                    fontSize = 22.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.driverTestTag("qty_value"),
                )
                PillButton("+", testTag = "qty_plus", onClick = {
                    // BUG-DET-05: `before` is the pre-increment value and roughly a third of the
                    // presses price the order from it, so the total is one unit behind the quantity.
                    val before = qty
                    qty += 1
                    total = if (Flake.hit(0.3, "detail_total_stale")) item.price * before else item.price * qty
                    logAction("detail_qty", "qty=$qty total=$total")
                })
                Text(
                    text = "Total ${formatPrice(total)}",
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.driverTestTag("total_value"),
                )
            }

            Divider12()
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                PillButton(
                    "Add to cart",
                    testTag = "add_to_cart_button",
                    selected = true,
                    modifier = Modifier.fillMaxWidth(),
                    onClick = {
                        primaryAction("add_to_cart") {
                            banner = "Added $qty × ${item.name}"
                            logAction("detail_add_to_cart", "item=${item.id} qty=$qty")
                        }
                    },
                )
                PillButton(
                    "Share",
                    testTag = "share_button",
                    modifier = Modifier.fillMaxWidth(),
                    onClick = {
                        primaryAction("share") {
                            banner = "Link copied"
                            logAction("detail_share", "item=${item.id}")
                        }
                    },
                )
                PillButton(
                    "Delete item",
                    testTag = "delete_button",
                    modifier = Modifier.fillMaxWidth(),
                    onClick = {
                        pendingDelete = true
                        confirmVisible = true
                        logAction("detail_delete_requested", "item=${item.id}")
                    },
                )
            }

            AppStore.lastDeletedName?.let {
                Text(
                    text = "Last deleted: $it",
                    fontSize = 12.sp,
                    modifier = Modifier.driverTestTag("last_deleted_readout"),
                )
            }
        }
    }

    Column(Modifier.fillMaxSize().driverTestTag("detail_root")) {
        AppTopBar(title = item.name, testTag = "detail_top_bar", onBack = onBack) {
            Text("#${item.id}", fontSize = 12.sp, modifier = Modifier.driverTestTag("detail_id_badge"))
        }

        if (landscape) {
            Row(Modifier.weight(1f).fillMaxWidth()) {
                Column(
                    modifier = Modifier
                        .width(300.dp)
                        .fillMaxHeight()
                        .background(MaterialTheme.colorScheme.surfaceVariant)
                        .padding(12.dp)
                        .driverTestTag("detail_gallery_pane"),
                ) {
                    Text("Gallery", fontWeight = FontWeight.Bold, modifier = Modifier.driverTestTag("gallery_title"))
                    Spacer(Modifier.height(8.dp))
                    (1..3).forEach { n ->
                        Box(
                            Modifier
                                .fillMaxWidth()
                                .height(72.dp)
                                .padding(vertical = 4.dp)
                                .background(MaterialTheme.colorScheme.tertiaryContainer)
                                .driverTestTag("gallery_thumb_$n"),
                        )
                    }
                }
                body(Modifier.weight(1f).fillMaxHeight())
            }
        } else {
            body(Modifier.weight(1f).fillMaxWidth())
        }
    }

    if (confirmVisible) {
        AlertDialog(
            onDismissRequest = { confirmVisible = false },
            // A Dialog is its own composition root in its own window, so it does not inherit the
            // activity's opt-in and has to map test tags to resource ids for itself.
            modifier = Modifier
                .semantics { testTagsAsResourceId = true }
                .driverTestTag("delete_dialog"),
            title = { Text("Delete this item?", modifier = Modifier.driverTestTag("delete_dialog_title")) },
            text = {
                Text(
                    "${item.name} will be removed from the catalog.",
                    modifier = Modifier.driverTestTag("delete_dialog_body"),
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        confirmVisible = false
                        pendingDelete = false
                        performDelete()
                    },
                    modifier = Modifier.driverTestTag("delete_confirm_button"),
                ) { Text("Delete") }
            },
            dismissButton = {
                TextButton(
                    onClick = {
                        confirmVisible = false
                        // Note: `pendingDelete` is deliberately left armed here — see BUG-DET-01.
                    },
                    modifier = Modifier.driverTestTag("delete_cancel_button"),
                ) { Text("Cancel") }
            },
        )
    }
}
