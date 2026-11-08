package com.ashura.tutor.ui

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
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
import com.ashura.tutor.data.StudyLibrary
import com.ashura.tutor.data.StudySet
import com.ashura.tutor.data.StudySubject
import com.ashura.tutor.domain.assessment.TestMode
import com.ashura.tutor.domain.assessment.formatClock
import com.ashura.tutor.domain.library.ImportStatus

/** Import notes, search their passages, delete them. Imported text is only ever shown as plain text. */
@Composable
fun LibraryScreen(
    libraryItems: List<LibraryItemEntity>,
    chunkCounts: Map<String, Int>?,
    addedTitles: Set<String>,
    onReindex: (String, String) -> Unit,
    state: LibraryUiState,
    studyLibrary: StudyLibrary?,
    onImport: (android.net.Uri) -> Unit,
    onQueryChange: (String) -> Unit,
    onDelete: (String) -> Unit,
    onTestNote: (String, String) -> Unit,
    onStartTest: (TestMode) -> Unit,
    onEditText: (String, String, String) -> Unit,
    onAddStudySet: (StudySet) -> Unit,
    onAddStudySubject: (StudySubject) -> Unit,
    onRemoveStudySet: (StudySet) -> Unit
) {
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> uri?.let(onImport) }
    var pendingDelete by remember { mutableStateOf<LibraryItemEntity?>(null) }
    var pendingRemove by remember { mutableStateOf<StudySet?>(null) }
    var editing by remember { mutableStateOf<LibraryItemEntity?>(null) }
    var editText by remember { mutableStateOf("") }
    var expandedSubject by rememberSaveable { mutableStateOf<String?>(null) }

    LazyColumn(
        Modifier.fillMaxSize().padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item { ScreenHeading(stringResource(R.string.library_title)) }
        item { Text(stringResource(R.string.library_intro), style = MaterialTheme.typography.bodyMedium) }

        item {
            Button(
                onClick = { picker.launch(importMimeTypes) },
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

        item { SectionHeading(stringResource(R.string.library_test_title)) }
        item {
            Text(
                stringResource(R.string.library_test_intro),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                TestMode.entries.forEach { mode ->
                    OutlinedButton(
                        onClick = { onStartTest(mode) },
                        enabled = !state.busy,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.Start) {
                            Text(testModeLabel(mode), style = MaterialTheme.typography.titleSmall)
                            Text(
                                stringResource(
                                    R.string.library_test_detail,
                                    mode.questionCount,
                                    formatClock(mode.durationSeconds)
                                ),
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }
            }
        }

        item { SectionHeading(stringResource(R.string.study_sets_title)) }
        if (studyLibrary == null) {
            item {
                Text(
                    stringResource(R.string.study_sets_loading),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        } else {
            item {
                Text(
                    stringResource(R.string.study_sets_intro, studyLibrary.count),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            items(studyLibrary.subjects, key = { "study-subject:${it.id}" }) { subject ->
                val expanded = expandedSubject == subject.id
                val addedCount = subject.sets.count { it.title in addedTitles }
                val allAdded = addedCount == subject.sets.size
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(
                            onClick = { expandedSubject = if (expanded) null else subject.id },
                            modifier = Modifier.weight(1f)
                        ) {
                            Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.Start) {
                                Text(subject.name, style = MaterialTheme.typography.titleSmall)
                                Text(
                                    stringResource(
                                        R.string.study_sets_level_added,
                                        subject.level, addedCount, subject.sets.size
                                    ),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                        if (allAdded) {
                            IconButton(onClick = {}, enabled = false) {
                                Icon(
                                    Icons.Default.Check,
                                    contentDescription = stringResource(R.string.study_sets_all_added_cd, subject.name),
                                    tint = MaterialTheme.colorScheme.primary
                                )
                            }
                        } else {
                            IconButton(
                                onClick = { onAddStudySubject(subject) },
                                enabled = !state.busy
                            ) {
                                Icon(
                                    Icons.Default.Add,
                                    contentDescription = stringResource(R.string.study_sets_add_all_cd, subject.name)
                                )
                            }
                        }
                    }
                    if (expanded) {
                        subject.sets.forEach { set ->
                            val added = set.title in addedTitles
                            Row(
                                Modifier.fillMaxWidth().padding(start = 8.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                Column(Modifier.weight(1f)) {
                                    Text(
                                        set.title,
                                        style = MaterialTheme.typography.bodyMedium,
                                        maxLines = 2,
                                        overflow = TextOverflow.Ellipsis
                                    )
                                    Text(
                                        stringResource(R.string.study_sets_meta, set.license),
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                    Text(
                                        set.source,
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis
                                    )
                                }
                                if (added) {
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Icon(
                                            Icons.Default.Check,
                                            contentDescription = null,
                                            tint = MaterialTheme.colorScheme.primary,
                                            modifier = Modifier.size(18.dp)
                                        )
                                        Text(
                                            stringResource(R.string.study_sets_added),
                                            style = MaterialTheme.typography.labelMedium,
                                            color = MaterialTheme.colorScheme.primary
                                        )
                                        IconButton(
                                            onClick = { pendingRemove = set },
                                            enabled = !state.busy
                                        ) {
                                            Icon(
                                                Icons.Default.Remove,
                                                contentDescription = stringResource(R.string.study_sets_remove_cd, set.title)
                                            )
                                        }
                                    }
                                } else {
                                    TextButton(onClick = { onAddStudySet(set) }, enabled = !state.busy) {
                                        Text(stringResource(R.string.study_sets_add_sign))
                                    }
                                }
                            }
                        }
                    }
                }
            }
            item {
                Text(
                    stringResource(R.string.study_sets_notice, studyLibrary.license),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }

        item { SectionHeading(stringResource(R.string.library_search_title)) }
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
                    if (chunkCounts == null) {
                        // First database read not finished: show the old character count rather than
                        // flashing a false "not indexed".
                        Text(
                            pluralStringResource(R.plurals.library_chars, item.body.length, item.body.length),
                            style = MaterialTheme.typography.bodySmall
                        )
                    } else {
                        val status = ImportStatus.of(item.body.length, chunkCounts[item.id] ?: 0)
                        val added = java.text.DateFormat.getDateInstance(java.text.DateFormat.MEDIUM)
                            .format(java.util.Date(item.createdAt))
                        Text(
                            if (status.indexed) {
                                stringResource(R.string.library_status_indexed, status.sizeLabel, status.passages, added)
                            } else {
                                stringResource(R.string.library_status_not_indexed, status.sizeLabel, added)
                            },
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }
                if (chunkCounts != null && (chunkCounts[item.id] ?: 0) == 0) {
                    TextButton(onClick = { onReindex(item.id, item.title) }) {
                        Text(stringResource(R.string.library_reindex))
                    }
                }
                TextButton(onClick = { onTestNote(item.id, item.title) }) { Text(stringResource(R.string.library_test)) }
                IconButton(onClick = { editText = item.body; editing = item }) {
                    Icon(Icons.Default.Edit, contentDescription = stringResource(R.string.library_edit_cd, item.title))
                }
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

    editing?.let { item ->
        AlertDialog(
            onDismissRequest = { editing = null },
            title = { Text(stringResource(R.string.library_edit_title)) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(stringResource(R.string.library_edit_body, item.title), style = MaterialTheme.typography.bodySmall)
                    OutlinedTextField(
                        value = editText,
                        onValueChange = { editText = it },
                        modifier = Modifier.fillMaxWidth().heightIn(min = 160.dp),
                        maxLines = 12
                    )
                }
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        val current = item
                        editing = null
                        if (editText.isNotBlank()) onEditText(current.id, current.title, editText)
                    },
                    enabled = editText.isNotBlank()
                ) { Text(stringResource(R.string.action_save)) }
            },
            dismissButton = {
                TextButton(onClick = { editing = null }) { Text(stringResource(R.string.action_cancel)) }
            }
        )
    }

    pendingRemove?.let { set ->
        AlertDialog(
            onDismissRequest = { pendingRemove = null },
            title = { Text(stringResource(R.string.study_sets_remove_title)) },
            text = { Text(stringResource(R.string.study_sets_remove_body, set.title)) },
            confirmButton = {
                TextButton(
                    onClick = {
                        pendingRemove = null
                        onRemoveStudySet(set)
                    }
                ) { Text(stringResource(R.string.study_sets_remove_confirm)) }
            },
            dismissButton = {
                TextButton(onClick = { pendingRemove = null }) { Text(stringResource(R.string.action_cancel)) }
            }
        )
    }
}
