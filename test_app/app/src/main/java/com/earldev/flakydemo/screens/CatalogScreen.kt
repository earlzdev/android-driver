package com.earldev.flakydemo.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
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
import com.earldev.flakydemo.core.Item
import com.earldev.flakydemo.core.formatPrice
import com.earldev.flakydemo.core.logAction
import com.earldev.flakydemo.core.logScreen
import com.earldev.flakydemo.ui.AppTopBar
import com.earldev.flakydemo.ui.PillButton
import com.earldev.flakydemo.ui.driverTestTag
import com.earldev.flakydemo.ui.isLandscape
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private val FILTERS = listOf("All", "In stock", "On sale")
private val SORTS = listOf("Name", "Price")

/**
 * Screen 3 — catalog.
 *
 * Bugs planted here: BUG-CAT-01 (search results for a stale query), BUG-CAT-02 (tapping a row right
 * after a filter change opens the wrong item or crashes), BUG-CAT-03 (query and scroll lost on
 * rotation), BUG-CAT-04 (Load more sometimes appends duplicates), BUG-CAT-05 (landscape two-column
 * layout drops the last row when the count is odd).
 */
@Composable
fun CatalogScreen(onBack: () -> Unit, onOpenItem: (Int) -> Unit) {
    // BUG-CAT-03: the query, the filter and the list position are all plain `remember`, so a
    // rotation clears the search box and jumps the list back to the top.
    var query by remember { mutableStateOf("") }
    var filter by remember { mutableStateOf(FILTERS.first()) }
    var sort by remember { mutableStateOf(SORTS.first()) }

    val visible = remember { mutableStateListOf<Item>() }
    var pageSize by remember { mutableIntStateOf(20) }
    var searching by remember { mutableStateOf(false) }
    var lastAppliedQuery by remember { mutableStateOf("") }
    var filterChangedAt by remember { mutableStateOf(0L) }

    val listState = rememberLazyListState()
    val scope = rememberCoroutineScope()
    val landscape = isLandscape()

    fun matching(q: String, f: String, s: String): List<Item> {
        val base = AppStore.catalog.filter { item ->
            val byQuery = q.isBlank() || item.name.contains(q, ignoreCase = true) ||
                item.category.contains(q, ignoreCase = true)
            val byFilter = when (f) {
                "In stock" -> item.inStock
                "On sale" -> item.onSale
                else -> true
            }
            byQuery && byFilter
        }
        return if (s == "Price") base.sortedBy { it.price } else base.sortedBy { it.name }
    }

    fun recompute(q: String, f: String, s: String) {
        searching = true
        scope.launch {
            // BUG-CAT-01: each keystroke starts its own delayed job and nothing cancels the previous
            // one, so with a variable delay a slower earlier job can land last and repaint the list
            // with results for a query the user has already moved past.
            delay(Flake.jitter(120, 420))
            val result = matching(q, f, s)
            visible.clear()
            visible.addAll(result)
            lastAppliedQuery = q
            searching = false
            logAction("catalog_search", "query=$q applied=$q count=${result.size} filter=$f")
        }
    }

    LaunchedEffect(Unit) {
        visible.clear()
        visible.addAll(matching("", FILTERS.first(), SORTS.first()))
        logScreen("catalog", "count=${visible.size}")
    }

    val shown = visible.take(pageSize)

    @Composable
    fun itemRow(item: Item, index: Int) {
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 4.dp)
                .clickable {
                    // BUG-CAT-02: the tap resolves the row through its *position* in the list that
                    // was on screen when the row was composed. A filter change that lands between
                    // composition and tap shifts everything, so the wrong detail screen opens — and
                    // when the list got shorter, the index is out of bounds and the app crashes.
                    val fresh = matching(query, filter, sort)
                    val sinceFilter = System.currentTimeMillis() - filterChangedAt
                    val target = if (sinceFilter < 400) fresh[index] else item
                    logAction("catalog_open", "index=$index tapped=${item.id} opening=${target.id}")
                    onOpenItem(target.id)
                }
                .driverTestTag("catalog_item_${item.id}"),
        ) {
            Row(
                modifier = Modifier.padding(12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(
                        text = item.name,
                        fontWeight = FontWeight.SemiBold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.driverTestTag("item_name_${item.id}"),
                    )
                    Text(
                        text = item.category,
                        fontSize = 12.sp,
                        modifier = Modifier.driverTestTag("item_category_${item.id}"),
                    )
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(
                        text = formatPrice(item.price),
                        fontWeight = FontWeight.Bold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.driverTestTag("item_price_${item.id}"),
                    )
                    Text(
                        text = if (item.inStock) "In stock" else "Backorder",
                        fontSize = 11.sp,
                        color = if (item.inStock) {
                            MaterialTheme.colorScheme.primary
                        } else {
                            MaterialTheme.colorScheme.error
                        },
                        modifier = Modifier.driverTestTag("item_stock_${item.id}"),
                    )
                }
            }
        }
    }

    Column(Modifier.fillMaxSize().driverTestTag("catalog_root")) {
        AppTopBar(title = "Catalog", testTag = "catalog_top_bar", onBack = onBack) {
            Text(
                text = "${visible.size} found",
                fontSize = 12.sp,
                modifier = Modifier.driverTestTag("result_count"),
            )
        }

        Column(
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            OutlinedTextField(
                value = query,
                onValueChange = {
                    query = it
                    recompute(it, filter, sort)
                },
                label = { Text("Search") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().driverTestTag("search_field"),
            )

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FILTERS.forEach { f ->
                    PillButton(
                        label = f,
                        testTag = "filter_chip_${f.replace(' ', '_')}",
                        selected = filter == f,
                        onClick = {
                            filter = f
                            filterChangedAt = System.currentTimeMillis()
                            logAction("catalog_filter", "filter=$f")
                            recompute(query, f, sort)
                        },
                    )
                }
                Spacer(Modifier.weight(1f))
                PillButton(
                    label = "Sort: $sort",
                    testTag = "sort_toggle",
                    onClick = {
                        val next = if (sort == "Name") "Price" else "Name"
                        sort = next
                        logAction("catalog_sort", "sort=$next")
                        recompute(query, filter, next)
                    },
                )
            }

            if (searching) {
                Text("Searching…", modifier = Modifier.driverTestTag("search_progress"))
            }
            Text(
                text = "Showing ${shown.size} of ${visible.size} · query \"$lastAppliedQuery\"",
                fontSize = 12.sp,
                modifier = Modifier.driverTestTag("catalog_summary"),
            )
        }

        if (shown.isEmpty()) {
            Box(
                modifier = Modifier.weight(1f).fillMaxWidth().driverTestTag("catalog_empty_state"),
                contentAlignment = Alignment.Center,
            ) {
                Text("No items match that search.", modifier = Modifier.driverTestTag("empty_message"))
            }
        } else if (landscape) {
            // BUG-CAT-05: the two-column landscape layout pairs rows up and iterates over the pairs,
            // but drops the tail when the count is odd — so the last item of an odd-length result
            // set is missing in landscape and present in portrait.
            val pairs = shown.chunked(2).filter { it.size == 2 }
            LazyColumn(
                state = listState,
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp)
                    .driverTestTag("catalog_list"),
            ) {
                items(pairs.size) { row ->
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Box(Modifier.weight(1f)) { itemRow(pairs[row][0], row * 2) }
                        Box(Modifier.weight(1f)) { itemRow(pairs[row][1], row * 2 + 1) }
                    }
                }
                item {
                    PillButton(
                        "Load more",
                        testTag = "load_more_button",
                        modifier = Modifier.fillMaxWidth().padding(vertical = 12.dp),
                        onClick = { loadMore(visible, pageSize) { pageSize = it } },
                    )
                }
            }
        } else {
            LazyColumn(
                state = listState,
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp)
                    .driverTestTag("catalog_list"),
            ) {
                items(shown, key = { it.id }) { item ->
                    itemRow(item, shown.indexOf(item))
                }
                item {
                    PillButton(
                        "Load more",
                        testTag = "load_more_button",
                        modifier = Modifier.fillMaxWidth().padding(vertical = 12.dp),
                        onClick = { loadMore(visible, pageSize) { pageSize = it } },
                    )
                }
            }
        }
    }
}

/**
 * BUG-CAT-04: one press in three grows the window by two pages instead of one, so the "Showing N"
 * readout jumps by 20 and skips a page of rows entirely.
 */
private fun loadMore(visible: List<Item>, current: Int, apply: (Int) -> Unit) {
    val step = if (Flake.hit(0.33, "catalog_load_more_double")) 20 else 10
    val next = (current + step).coerceAtMost(visible.size.coerceAtLeast(current))
    logAction("catalog_load_more", "from=$current step=$step to=$next")
    apply(next)
}
