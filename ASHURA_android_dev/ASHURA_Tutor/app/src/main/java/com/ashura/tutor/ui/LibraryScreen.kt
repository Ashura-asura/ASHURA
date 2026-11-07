package com.ashura.tutor.ui

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.ashura.tutor.R
import com.ashura.tutor.data.LibraryItemEntity

/** Import notes, search their passages, delete them. Imported text is only ever shown as plain text. */
@Composable
fun LibraryScreen(
    libraryItems: List<LibraryItemEntity>,
    state: LibraryUiState,
    onImport: (android.net.Uri) -> Unit,
    onQueryChange: (String) -> Unit,
    onDelete: (String) -> Unit,
    onQuiz: (String, String) -> Unit
) {
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> uri?.let(onImport) }
    var pendingDelete by remember { mutableStateOf<LibraryItemEntity?>(null) }

    LazyColumn(
        Modifier.fillMaxSize().padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item { ScreenHeading(stringResource(R.string.library_title)) }
        item { Text(stringResource(R.string.library_intro), style = MaterialTheme.typography.bodyMedium) }

        item {
            Button(
                onClick = {
                    picker.launch(
                        arrayOf(
                            "text/plain", "text/markdown", "text/x-markdown",
                            "application/msword",
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            "application/vnd.ms-excel",
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            "application/vnd.ms-powerpoint",
                            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                        )
                    )
                },
                enabled = !state.busy, modifier = Modifier.fillMaxWidth()
            ) {
                Text(stringResource(if (state.busy) R.string.library_importing else R.string.library_import))
            }
        }
        state.message?.let { message ->
            item {
                Text(
                    message, color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }
                )
            }
        }

        item {
            OutlinedTextField(
                value = state.query, onValueChange = onQueryChange, singleLine = true,
                label = { Text(stringResource(R.string.library_search_label)) }, modifier = Modifier.fillMaxWidth()
            )
        }
        if (state.searched && state.results.isEmpty()) {
            item { Text(stringResource(R.string.library_no_matches)) }
        }
        items(state.results, key = { "${it.itemId}:${it.ordinal}" }) { hit ->
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    stringResource(R.string.library_passage, hit.title, hit.ordinal + 1),
                    style = MaterialTheme.typography.titleSmall
                )
                Text(hit.text, maxLines = 5, overflow = TextOverflow.Ellipsis, style = MaterialTheme.typography.bodyMedium)
            }
        }

        item {
            SectionHeading(stringResource(R.string.library_imported_count, libraryItems.size))
        }
        if (libraryItems.isEmpty()) {
            item { Text(stringResource(R.string.library_empty)) }
        }
        items(libraryItems, key = { it.id }) { item ->
            Row(
                Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column(Modifier.weight(1f)) {
                    Text(item.title, style = MaterialTheme.typography.titleMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(
                        pluralStringResource(R.plurals.library_chars, item.body.length, item.body.length),
                        style = MaterialTheme.typography.bodySmall
                    )
                }
                TextButton(onClick = { onQuiz(item.id, item.title) }) { Text(stringResource(R.string.library_quiz)) }
                IconButton(onClick = { pendingDelete = item }) {
                    Icon(Icons.Default.Delete, contentDescription = stringResource(R.string.library_delete_cd, item.title))
                }
            }
        }
    }

    pendingDelete?.let { item ->
        AlertDialog(
            onDismissRequest = { pendingDelete = null },
            title = { Text(stringResource(R.string.library_delete_title)) },
            text = { Text(stringResource(R.string.library_delete_body, item.title)) },
            confirmButton = {
                TextButton(onClick = { pendingDelete = null; onDelete(item.id) }) {
                    Text(stringResource(R.string.action_delete))
                }
            },
            dismissButton = {
                TextButton(onClick = { pendingDelete = null }) { Text(stringResource(R.string.action_cancel)) }
            }
        )
    }
}
