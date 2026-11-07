package com.ashura.tutor.ui

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.ashura.tutor.data.LibraryItemEntity

/** Import text/Markdown notes, search their passages, delete them. Imported text is shown as plain text only. */
@Composable
fun LibraryScreen(
    items: List<LibraryItemEntity>,
    state: LibraryUiState,
    onImport: (android.net.Uri) -> Unit,
    onQueryChange: (String) -> Unit,
    onDelete: (String) -> Unit,
    onQuiz: (String, String) -> Unit
) {
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> uri?.let(onImport) }
    var pendingDelete by remember { mutableStateOf<LibraryItemEntity?>(null) }

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("Your Library", style = MaterialTheme.typography.headlineMedium, modifier = Modifier.semantics { heading() })
        Text(
            "Import .txt or .md notes. They stay on this device and are searched offline. PDF, Word and photo (OCR) import are not built yet.",
            style = MaterialTheme.typography.bodyMedium
        )
        Button(
            onClick = { picker.launch(arrayOf("text/*", "application/octet-stream")) },
            enabled = !state.busy, modifier = Modifier.fillMaxWidth()
        ) { Text(if (state.busy) "Importing…" else "Import a note") }
        state.message?.let { Text(it, color = MaterialTheme.colorScheme.primary, modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }) }

        OutlinedTextField(
            value = state.query, onValueChange = onQueryChange, singleLine = true,
            label = { Text("Search your notes") }, modifier = Modifier.fillMaxWidth()
        )
        if (state.searched && state.results.isEmpty()) Text("No matching passages.")
        state.results.forEach { hit ->
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("${hit.title} · passage ${hit.ordinal + 1}", style = MaterialTheme.typography.titleSmall)
                Text(hit.text, maxLines = 5, overflow = TextOverflow.Ellipsis, style = MaterialTheme.typography.bodyMedium)
            }
        }

        Text("Imported notes (${items.size})", style = MaterialTheme.typography.titleLarge, modifier = Modifier.semantics { heading() })
        if (items.isEmpty()) Text("Nothing imported yet.")
        items.forEach { item ->
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
                Column(Modifier.weight(1f)) {
                    Text(item.title, style = MaterialTheme.typography.titleMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text("${item.body.length} characters", style = MaterialTheme.typography.bodySmall)
                }
                TextButton(onClick = { onQuiz(item.id, item.title) }) { Text("Quiz me") }
                IconButton(onClick = { pendingDelete = item }) {
                    Icon(Icons.Default.Delete, contentDescription = "Delete ${item.title}")
                }
            }
        }
    }

    pendingDelete?.let { item ->
        AlertDialog(
            onDismissRequest = { pendingDelete = null },
            title = { Text("Delete this note?") },
            text = { Text("“${item.title}” and its passages will be removed from this device.") },
            confirmButton = { TextButton(onClick = { pendingDelete = null; onDelete(item.id) }) { Text("Delete") } },
            dismissButton = { TextButton(onClick = { pendingDelete = null }) { Text("Cancel") } }
        )
    }
}
