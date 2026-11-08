package com.ashura.tutor.ui

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
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
import androidx.compose.ui.graphics.vector.ImageVector
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

/** Top-level Library sections (spec §3.4). Kept as a string name so rotation preserves the choice. */
private enum class LibrarySection { MATERIAL, SETS, TESTS }

/** Filter inside the material list; "recent" means added in the last seven days. */
private enum class MaterialFilter { ALL, RECENT, DOCUMENTS, NOTES }

private const val RECENT_WINDOW_MILLIS = 7L * 24 * 60 * 60 * 1000

/** Import material, search it, inspect an item, manage built-in study sets and start timed tests. */
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
    var section by rememberSaveable { mutableStateOf(LibrarySection.MATERIAL.name) }
    var materialFilter by rememberSaveable { mutableStateOf(MaterialFilter.ALL.name) }
    var pendingDelete by remember { mutableStateOf<LibraryItemEntity?>(null) }
    var pendingRemove by remember { mutableStateOf<StudySet?>(null) }
    var editing by remember { mutableStateOf<LibraryItemEntity?>(null) }
    var editText by remember { mutableStateOf("") }
    var expandedSubject by rememberSaveable { mutableStateOf<String?>(null) }
    var selectedItem by remember { mutableStateOf<LibraryItemEntity?>(null) }
    val recentCutoff = remember { System.currentTimeMillis() - RECENT_WINDOW_MILLIS }

    LazyColumn(
        Modifier.fillMaxSize().padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item { ScreenHeading(stringResource(R.string.library_title)) }
        item {
            Text(
                stringResource(R.string.library_intro),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
        item {
            Row(
                Modifier.horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                SectionChip(
                    label = stringResource(R.string.library_section_material),
                    selected = section == LibrarySection.MATERIAL.name,
                    onClick = { section = LibrarySection.MATERIAL.name }
                )
                SectionChip(
                    label = stringResource(R.string.library_section_sets),
                    selected = section == LibrarySection.SETS.name,
                    onClick = { section = LibrarySection.SETS.name }
                )
                SectionChip(
                    label = stringResource(R.string.library_section_tests),
                    selected = section == LibrarySection.TESTS.name,
                    onClick = { section = LibrarySection.TESTS.name }
                )
            }
        }

        when (LibrarySection.valueOf(section)) {
            LibrarySection.MATERIAL -> {
                item {
                    Button(
                        onClick = { picker.launch(importMimeTypes) },
                        enabled = !state.busy,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text(stringResource(if (state.busy) R.string.library_importing else R.string.library_import))
                    }
                }
                state.message?.let { message ->
                    item {
                        Text(
                            message,
                            color = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }
                        )
                    }
                }
                item {
                    OutlinedTextField(
                        value = state.query,
                        onValueChange = onQueryChange,
                        singleLine = true,
                        label = { Text(stringResource(R.string.library_search_label)) },
                        modifier = Modifier.fillMaxWidth()
                    )
                }
                if (state.searched) {
                    if (state.results.isEmpty()) {
                        item { Text(stringResource(R.string.library_no_matches)) }
                    }
                    items(state.results, key = { "hit:${it.itemId}:${it.ordinal}" }) { hit ->
                        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Text(
                                stringResource(R.string.library_passage, hit.title, hit.ordinal + 1),
                                style = MaterialTheme.typography.titleSmall
                            )
                            Text(
                                hit.text,
                                maxLines = 5,
                                overflow = TextOverflow.Ellipsis,
                                style = MaterialTheme.typography.bodyMedium
                            )
                        }
                    }
                } else {
                    item {
                        Row(
                            Modifier.horizontalScroll(rememberScrollState()),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            SectionChip(
                                label = stringResource(R.string.library_filter_all),
                                selected = materialFilter == MaterialFilter.ALL.name,
                                onClick = { materialFilter = MaterialFilter.ALL.name }
                            )
                            SectionChip(
                                label = stringResource(R.string.library_filter_recent),
                                selected = materialFilter == MaterialFilter.RECENT.name,
                                onClick = { materialFilter = MaterialFilter.RECENT.name }
                            )
                            SectionChip(
                                label = stringResource(R.string.library_filter_documents),
                                selected = materialFilter == MaterialFilter.DOCUMENTS.name,
                                onClick = { materialFilter = MaterialFilter.DOCUMENTS.name }
                            )
                            SectionChip(
                                label = stringResource(R.string.library_filter_notes),
                                selected = materialFilter == MaterialFilter.NOTES.name,
                                onClick = { materialFilter = MaterialFilter.NOTES.name }
                            )
                        }
                    }
                    item {
                        SectionHeading(stringResource(R.string.library_imported_count, libraryItems.size))
                    }
                    val visible = libraryItems.filter { item ->
                        when (MaterialFilter.valueOf(materialFilter)) {
                            MaterialFilter.ALL -> true
                            MaterialFilter.RECENT -> item.createdAt >= recentCutoff
                            MaterialFilter.DOCUMENTS -> !isNoteMime(item.mimeType)
                            MaterialFilter.NOTES -> isNoteMime(item.mimeType)
                        }
                    }
                    if (libraryItems.isEmpty()) {
                        item { Text(stringResource(R.string.library_empty)) }
                    } else if (visible.isEmpty()) {
                        item { Text(stringResource(R.string.library_filter_empty)) }
                    }
                    items(visible, key = { it.id }) { item ->
                        LibraryItemRow(
                            item = item,
                            chunkCounts = chunkCounts,
                            onClick = { selectedItem = item }
                        )
                    }
                }
            }

            LibrarySection.SETS -> {
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
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
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
            }

            LibrarySection.TESTS -> {
                item { SectionHeading(stringResource(R.string.library_test_title)) }
                item {
                    Text(
                        stringResource(R.string.library_test_intro),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                items(TestMode.entries, key = { "mode:${it.name}" }) { mode ->
                    OutlinedButton(
                        onClick = { onStartTest(mode) },
                        enabled = !state.busy,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Row(
                            Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column(horizontalAlignment = Alignment.Start) {
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
                            Icon(Icons.Default.ChevronRight, contentDescription = null)
                        }
                    }
                }
            }
        }
    }

    selectedItem?.let { item ->
        val status = chunkCounts?.let { ImportStatus.of(item.body.length, it[item.id] ?: 0) }
        val added = java.text.DateFormat.getDateInstance(java.text.DateFormat.MEDIUM)
            .format(java.util.Date(item.createdAt))
        AlertDialog(
            onDismissRequest = { selectedItem = null },
            title = { Text(item.title) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(
                        stringResource(R.string.library_detail_format, formatLabel(item.mimeType)),
                        style = MaterialTheme.typography.bodyMedium
                    )
                    Text(
                        if (status != null && status.indexed) {
                            stringResource(R.string.library_status_indexed, status.sizeLabel, status.passages, added)
                        } else {
                            stringResource(R.string.library_status_not_indexed, status?.sizeLabel ?: "", added)
                        },
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        stringResource(R.string.library_detail_source),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    // Actions live in the body so four of them never overflow the dialog action row
                    // on a narrow phone.
                    LibraryDetailAction(stringResource(R.string.library_test)) {
                        selectedItem = null
                        onTestNote(item.id, item.title)
                    }
                    LibraryDetailAction(stringResource(R.string.library_edit_short)) {
                        selectedItem = null
                        editText = item.body
                        editing = item
                    }
                    if (chunkCounts != null && (chunkCounts[item.id] ?: 0) == 0) {
                        LibraryDetailAction(stringResource(R.string.library_reindex)) {
                            selectedItem = null
                            onReindex(item.id, item.title)
                        }
                    }
                    LibraryDetailAction(stringResource(R.string.action_delete)) {
                        selectedItem = null
                        pendingDelete = item
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = { selectedItem = null }) {
                    Text(stringResource(R.string.action_close))
                }
            }
        )
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

@Composable
private fun SectionChip(label: String, selected: Boolean, onClick: () -> Unit) {
    FilterChip(selected = selected, onClick = onClick, label = { Text(label) })
}

@Composable
private fun LibraryDetailAction(label: String, onClick: () -> Unit) {
    TextButton(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Text(label, Modifier.fillMaxWidth(), textAlign = androidx.compose.ui.text.style.TextAlign.Start)
    }
}

/** One imported item: title plus format/size/date and index state. The whole row opens details. */
@Composable
private fun LibraryItemRow(
    item: LibraryItemEntity,
    chunkCounts: Map<String, Int>?,
    onClick: () -> Unit
) {
    Surface(
        shape = androidx.compose.foundation.shape.RoundedCornerShape(16.dp),
        color = MaterialTheme.colorScheme.surface,
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick)
    ) {
        Row(
            Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    item.title,
                    style = MaterialTheme.typography.titleMedium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
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
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            Icon(
                Icons.Default.ChevronRight,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

/** Text-like types are treated as notes; everything else (PDF, image, Office) as a document. */
private fun isNoteMime(mimeType: String): Boolean =
    mimeType.startsWith("text/") || mimeType == "application/octet-stream"

@Composable
private fun formatLabel(mimeType: String): String = when {
    mimeType == "application/pdf" -> "PDF"
    mimeType.startsWith("image/") -> stringResource(R.string.library_format_photo)
    mimeType == "application/msword" ||
        mimeType.startsWith("application/vnd.openxmlformats-officedocument.wordprocessingml") -> "Word"
    mimeType == "application/vnd.ms-excel" ||
        mimeType.startsWith("application/vnd.openxmlformats-officedocument.spreadsheetml") -> "Excel"
    mimeType == "application/vnd.ms-powerpoint" ||
        mimeType.startsWith("application/vnd.openxmlformats-officedocument.presentationml") -> "PowerPoint"
    mimeType == "text/markdown" || mimeType == "text/x-markdown" -> "Markdown"
    mimeType == "text/csv" || mimeType.startsWith("text/tab-separated") -> "CSV"
    else -> stringResource(R.string.library_format_text)
}
