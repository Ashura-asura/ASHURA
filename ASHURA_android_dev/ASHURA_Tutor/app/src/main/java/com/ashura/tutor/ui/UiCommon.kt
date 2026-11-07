package com.ashura.tutor.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics

/** Large screen title, exposed to accessibility services as a heading. */
@Composable
internal fun ScreenHeading(text: String, modifier: Modifier = Modifier) =
    Text(text, modifier = modifier.semantics { heading() }, style = MaterialTheme.typography.headlineMedium)

/** Section title inside a screen, exposed to accessibility services as a heading. */
@Composable
internal fun SectionHeading(text: String, modifier: Modifier = Modifier) =
    Text(text, modifier = modifier.semantics { heading() }, style = MaterialTheme.typography.titleLarge)
