package com.earldev.flakydemo.ui

import android.content.res.Configuration
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Names an element for the driver twice over: as a `testTag` (which surfaces as `resource-id` in the
 * hierarchy because the root opts into `testTagsAsResourceId`) and as a `contentDescription`. Either
 * `id=` or `desc=` selectors then resolve it, and `list_selectors` sees the literal either way.
 */
fun Modifier.driverTestTag(name: String): Modifier =
    this.testTag(name).semantics { contentDescription = name }

@Composable
fun isLandscape(): Boolean =
    LocalConfiguration.current.orientation == Configuration.ORIENTATION_LANDSCAPE

@Composable
fun AppTopBar(
    title: String,
    testTag: String,
    onBack: (() -> Unit)? = null,
    trailing: @Composable () -> Unit = {},
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.primaryContainer)
            .padding(horizontal = 12.dp, vertical = 10.dp)
            .driverTestTag(testTag),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (onBack != null) {
            Text(
                text = "< Back",
                fontWeight = FontWeight.Medium,
                modifier = Modifier
                    .clickable { onBack() }
                    .padding(end = 12.dp, top = 4.dp, bottom = 4.dp)
                    .driverTestTag("back_button"),
            )
        }
        Text(
            text = title,
            fontSize = 20.sp,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier
                .weight(1f)
                .driverTestTag("screen_title"),
        )
        trailing()
    }
}

@Composable
fun PillButton(
    label: String,
    testTag: String,
    selected: Boolean = false,
    enabled: Boolean = true,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    val scheme = MaterialTheme.colorScheme
    val bg = when {
        !enabled -> scheme.surfaceVariant
        selected -> scheme.primary
        else -> scheme.secondaryContainer
    }
    val fg = when {
        !enabled -> scheme.onSurfaceVariant.copy(alpha = 0.5f)
        selected -> scheme.onPrimary
        else -> scheme.onSecondaryContainer
    }
    Box(
        modifier = modifier
            .driverTestTag(testTag)
            .clip(RoundedCornerShape(18.dp))
            .background(bg)
            .clickable(enabled = enabled) { onClick() }
            .padding(horizontal = 16.dp, vertical = 10.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(text = label, color = fg, fontWeight = FontWeight.Medium, maxLines = 1)
    }
}

@Composable
fun StatCard(
    label: String,
    value: String,
    testTag: String,
    modifier: Modifier = Modifier,
) {
    Card(modifier = modifier.driverTestTag(testTag)) {
        Column(Modifier.padding(12.dp)) {
            Text(
                text = label,
                fontSize = 12.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.driverTestTag("${testTag}_label"),
            )
            Text(
                text = value,
                fontSize = 22.sp,
                fontWeight = FontWeight.Bold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.driverTestTag("${testTag}_value"),
            )
        }
    }
}

@Composable
fun Banner(text: String, testTag: String, tone: Color) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(tone.copy(alpha = 0.16f))
            .border(1.dp, tone, RoundedCornerShape(8.dp))
            .padding(12.dp)
            .driverTestTag(testTag),
    ) {
        Text(text = text, color = tone, modifier = Modifier.driverTestTag("${testTag}_text"))
    }
}

@Composable
fun SectionLabel(text: String, testTag: String) {
    Text(
        text = text,
        fontWeight = FontWeight.SemiBold,
        fontSize = 13.sp,
        modifier = Modifier
            .padding(top = 8.dp, bottom = 2.dp)
            .driverTestTag(testTag),
    )
}

@Composable
fun Divider12() {
    Box(
        Modifier
            .fillMaxWidth()
            .height(1.dp)
            .background(MaterialTheme.colorScheme.outlineVariant),
    )
}
