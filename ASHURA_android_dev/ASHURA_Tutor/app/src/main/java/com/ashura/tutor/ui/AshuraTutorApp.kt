package com.ashura.tutor.ui

import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.annotation.StringRes
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Book
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Insights
import androidx.compose.material.icons.filled.School
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
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
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.ashura.tutor.R
import java.text.DateFormat
import java.util.Date

private enum class Destination(@StringRes val labelRes: Int, val icon: ImageVector) {
    HOME(R.string.nav_home, Icons.Default.Home),
    TUTOR(R.string.nav_tutor, Icons.Default.School),
    LIBRARY(R.string.nav_library, Icons.Default.Book),
    PROGRESS(R.string.nav_progress, Icons.Default.Insights),
    SETTINGS(R.string.nav_settings, Icons.Default.Settings)
}

@Composable
fun AshuraTutorApp(viewModel: TutorViewModel) {
    // Only a String is saved across recreation; rich objects live in the ViewModel (rememberSaveable of a
    // non-Parcelable object would crash on process death / rotation).
    var selected by rememberSaveable { mutableStateOf(Destination.HOME.name) }
    val state by viewModel.state.collectAsState()
    val lesson by viewModel.lesson.collectAsState()
    val practice by viewModel.practice.collectAsState()
    val progress by viewModel.progress.collectAsState()
    val libraryState by viewModel.library.collectAsState()
    val libraryItems by viewModel.libraryItems.collectAsState()
    val settingsMessage by viewModel.settingsMessage.collectAsState()

    LaunchedEffect(Unit) { viewModel.openTutorTab.collect { selected = Destination.TUTOR.name } }

    BackHandler(enabled = practice.question != null) { viewModel.closePractice() }
    BackHandler(enabled = practice.question == null && lesson != null && selected == Destination.TUTOR.name) { viewModel.clearLesson() }

    Scaffold(
        bottomBar = {
            NavigationBar {
                Destination.entries.forEach { item ->
                    NavigationBarItem(
                        selected = selected == item.name,
                        onClick = { selected = item.name },
                        icon = { Icon(item.icon, contentDescription = null) },
                        label = { Text(stringResource(item.labelRes)) }
                    )
                }
            }
        }
    ) { insets ->
        Surface(Modifier.fillMaxSize().padding(insets).consumeWindowInsets(insets), color = MaterialTheme.colorScheme.background) {
            when (Destination.valueOf(selected)) {
                Destination.HOME -> HomeScreen(
                    recommendedTitle = progress.recommendedTitle, dueCount = progress.dueCount,
                    onContinue = {
                        progress.recommendedTopicId?.let(viewModel::startTopic)
                        selected = Destination.TUTOR.name
                    },
                    onOpenTutor = { selected = Destination.TUTOR.name }
                )
                Destination.TUTOR -> when {
                    practice.question != null -> PracticeScreen(
                        state = practice,
                        onSubmit = viewModel::submitAnswer,
                        onSelfAssess = viewModel::submitSelfAssessed,
                        onHint = viewModel::revealHint,
                        onShowSolution = viewModel::showSolution,
                        onNext = viewModel::nextQuizQuestion,
                        onClose = viewModel::closePractice
                    )
                    lesson != null -> LessonScreen(
                        lesson = lesson,
                        onStartPractice = viewModel::openPractice,
                        onNavigateHome = viewModel::clearLesson
                    )
                    else -> TutorScreen(
                        question = state.question, answer = state.answer, limitation = state.limitation, citations = state.citations,
                        isBusy = state.isBusy, error = state.error,
                        topics = viewModel.topics, recommendedId = progress.recommendedTopicId,
                        onQuestionChange = viewModel::updateQuestion, onAsk = viewModel::ask,
                        onCancel = viewModel::cancelAsk, onStartTopic = viewModel::startTopic
                    )
                }
                Destination.LIBRARY -> LibraryScreen(
                    libraryItems = libraryItems, state = libraryState,
                    onImport = viewModel::importDocument, onQueryChange = viewModel::updateLibraryQuery,
                    onDelete = viewModel::deleteLibraryItem, onQuiz = viewModel::startNoteQuiz
                )
                Destination.PROGRESS -> ProgressScreen(progress)
                Destination.SETTINGS -> SettingsScreen(
                    message = settingsMessage, onExport = viewModel::exportData,
                    onDeleteAll = { viewModel.deleteAllData { selected = Destination.HOME.name } }
                )
            }
        }
    }
}

@Composable
private fun HomeScreen(recommendedTitle: String?, dueCount: Int, onContinue: () -> Unit, onOpenTutor: () -> Unit) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text(stringResource(R.string.app_name), style = MaterialTheme.typography.headlineLarge, modifier = Modifier.semantics { heading() })
        Text(stringResource(R.string.home_tagline), style = MaterialTheme.typography.titleMedium)
        Text(stringResource(R.string.home_description))
        if (recommendedTitle != null) {
            Button(onClick = onContinue, modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(R.string.home_next_lesson, recommendedTitle))
            }
        } else {
            Text(stringResource(R.string.home_all_mastered))
        }
        if (dueCount > 0) Text(pluralStringResource(R.plurals.home_due, dueCount, dueCount))
        OutlinedButton(onClick = onOpenTutor, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.home_ask)) }
    }
}

@Composable
private fun TutorScreen(
    question: String, answer: String?, limitation: String?, citations: List<String>, isBusy: Boolean, error: String?,
    topics: List<TopicSummary>, recommendedId: String?,
    onQuestionChange: (String) -> Unit, onAsk: () -> Unit, onCancel: () -> Unit, onStartTopic: (String) -> Unit
) {
    LazyColumn(
        Modifier.fillMaxSize().imePadding().padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item { ScreenHeading(stringResource(R.string.tutor_title)) }
        item { Text(stringResource(R.string.tutor_intro)) }
        item {
            OutlinedTextField(
                value = question, onValueChange = onQuestionChange, modifier = Modifier.fillMaxWidth(),
                label = { Text(stringResource(R.string.tutor_question_label)) }, minLines = 3
            )
        }
        item {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Button(onClick = onAsk, enabled = !isBusy && question.isNotBlank()) {
                    Text(if (isBusy) stringResource(R.string.tutor_working) else stringResource(R.string.tutor_ask))
                }
                if (isBusy) TextButton(onClick = onCancel) { Text(stringResource(R.string.tutor_cancel)) }
            }
        }
        if (isBusy) item { CircularProgressIndicator() }
        error?.let { message -> item { Text(message, color = MaterialTheme.colorScheme.error) } }
        answer?.let { text ->
            item {
                Text(stringResource(R.string.tutor_response), style = MaterialTheme.typography.titleLarge, modifier = Modifier.semantics { heading() })
            }
            item { Text(text) }
            limitation?.let { l ->
                item { Text(l, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            }
            if (citations.isNotEmpty()) {
                item {
                    Text(stringResource(R.string.tutor_sources), style = MaterialTheme.typography.titleSmall, modifier = Modifier.semantics { heading() })
                }
                items(citations) { c -> Text(c, style = MaterialTheme.typography.bodySmall) }
            }
        }
        item { SectionHeading(stringResource(R.string.tutor_lessons)) }
        items(topics, key = { it.id }) { t ->
            val recommended = t.id == recommendedId
            val label = buildString {
                append(t.title)
                if (recommended) append(stringResource(R.string.tutor_recommended_suffix))
                if (t.prerequisiteTitles.isNotEmpty()) {
                    append('\n')
                    append(stringResource(R.string.tutor_builds_on, t.prerequisiteTitles.joinToString()))
                }
            }
            if (recommended) {
                Button(onClick = { onStartTopic(t.id) }, modifier = Modifier.fillMaxWidth()) { Text(label) }
            } else {
                OutlinedButton(onClick = { onStartTopic(t.id) }, modifier = Modifier.fillMaxWidth()) { Text(label) }
            }
        }
    }
}

@Composable
private fun ProgressScreen(progress: ProgressUiState) {
    val dateFormat = remember { DateFormat.getDateInstance(DateFormat.MEDIUM) }
    LazyColumn(
        Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item { ScreenHeading(stringResource(R.string.progress_title)) }
        item { Text(stringResource(R.string.progress_explainer), style = MaterialTheme.typography.bodySmall) }
        if (progress.topics.isEmpty()) item { Text(stringResource(R.string.progress_empty)) }
        items(progress.topics, key = { it.topicId }) { t ->
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(t.title, style = MaterialTheme.typography.titleMedium)
                LinearProgressIndicator(progress = { t.mastery.toFloat().coerceIn(0f, 1f) }, modifier = Modifier.fillMaxWidth())
                val review = if (t.due) stringResource(R.string.progress_review_due)
                else stringResource(R.string.progress_next_review, dateFormat.format(Date(t.nextReviewAt)))
                Text(
                    stringResource(R.string.progress_line, (t.mastery * 100).toInt(), (t.confidence * 100).toInt(), review),
                    style = MaterialTheme.typography.bodySmall
                )
            }
        }
        if (progress.misconceptions.isNotEmpty()) {
            item { SectionHeading(stringResource(R.string.progress_misconceptions)) }
            items(progress.misconceptions) { Text("• $it") }
        }
    }
}

@Composable
private fun SettingsScreen(message: String?, onExport: (android.net.Uri) -> Unit, onDeleteAll: () -> Unit) {
    var confirm by remember { mutableStateOf(false) }
    val exporter = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri -> uri?.let(onExport) }
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        ScreenHeading(stringResource(R.string.settings_title))
        Text(stringResource(R.string.settings_intro))
        OutlinedButton(onClick = { exporter.launch("ashura-tutor-export.json") }, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.settings_export))
        }
        message?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
        OutlinedButton(onClick = { confirm = true }, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.settings_delete_all))
        }
    }
    if (confirm) {
        AlertDialog(
            onDismissRequest = { confirm = false },
            title = { Text(stringResource(R.string.settings_delete_title)) },
            text = { Text(stringResource(R.string.settings_delete_body)) },
            confirmButton = { TextButton(onClick = { confirm = false; onDeleteAll() }) { Text(stringResource(R.string.action_delete)) } },
            dismissButton = { TextButton(onClick = { confirm = false }) { Text(stringResource(R.string.action_cancel)) } }
        )
    }
}
