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

/**
 * One list of import types shared by Library and Home, so a format added to the reader cannot be
 * missing from one picker. Legacy Office types are included only so the user sees the app's clear
 * rejection message instead of the file disappearing from the picker.
 */
internal val importMimeTypes = arrayOf(
    "text/plain", "text/markdown", "text/x-markdown",
    "text/csv", "text/comma-separated-values", "text/tab-separated-values",
    "application/pdf", "image/png", "image/jpeg", "image/webp",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)
