package com.ashura.tutor.ui

import android.text.format.Formatter
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.annotation.StringRes
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
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
import androidx.compose.material3.FilterChip
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.ashura.tutor.R
import com.ashura.tutor.data.model.ModelState
import com.ashura.tutor.data.profile.LearnerProfile
import com.ashura.tutor.domain.LearnerLevel
import com.ashura.tutor.domain.ResponseMode
import com.ashura.tutor.domain.StructuredAnswer
import com.ashura.tutor.domain.TutorStyle
import com.ashura.tutor.domain.runtime.ModelCatalog
import com.ashura.tutor.domain.runtime.ModelManifest
import com.ashura.tutor.domain.runtime.RamTier
import com.ashura.tutor.domain.runtime.RuntimeMetrics
import com.ashura.tutor.domain.runtime.rank
import kotlinx.coroutines.delay
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
    val modelState by viewModel.modelState.collectAsState()
    val profile by viewModel.profile.collectAsState()
    val runtimeMetrics by viewModel.runtimeMetrics.collectAsState()

    LaunchedEffect(Unit) { viewModel.openTutorTab.collect { selected = Destination.TUTOR.name } }

    BackHandler(enabled = practice.question != null) { viewModel.closePractice() }
    BackHandler(enabled = practice.question == null && lesson != null && selected == Destination.TUTOR.name) { viewModel.clearLesson() }

    var showSplash by rememberSaveable { mutableStateOf(true) }
    LaunchedEffect(Unit) { delay(1_800); showSplash = false }

    Box(Modifier.fillMaxSize()) {
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
                        question = state.question, answer = state.answer, limitation = state.limitation,
                        citations = state.citations, mode = state.mode,
                        isBusy = state.isBusy, error = state.error,
                        modelLoaded = (modelState as? ModelState.Ready)?.loaded == true,
                        style = profile.style,
                        onToggleStyle = {
                            viewModel.setTutorStyle(
                                if (profile.style == TutorStyle.SOCRATIC) TutorStyle.DIRECT else TutorStyle.SOCRATIC
                            )
                        },
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
                    message = settingsMessage,
                    modelState = modelState,
                    catalog = viewModel.modelCatalog,
                    deviceTier = viewModel.deviceTier,
                    onDownloadModel = viewModel::downloadModel,
                    onImportModel = viewModel::importModel,
                    onLoadModel = viewModel::loadModel,
                    onUnloadModel = viewModel::unloadModel,
                    onDeleteModel = viewModel::deleteModel,
                    onCancelModel = viewModel::cancelModelDownload,
                    onExport = viewModel::exportData,
                    onDeleteAll = { viewModel.deleteAllData { selected = Destination.HOME.name } },
                    profile = profile,
                    onLevelChange = viewModel::setLearnerLevel,
                    onStyleChange = viewModel::setTutorStyle,
                    onLanguageChange = viewModel::setResponseLanguage,
                    metrics = runtimeMetrics,
                    freeStorageBytes = viewModel.freeStorageBytes()
                )
            }
        }
    }
    AnimatedVisibility(
        visible = showSplash,
        enter = fadeIn(tween(250)),
        exit = fadeOut(tween(450))
    ) { BrandSplash() }
    }
}

@Composable
private fun BrandSplash() {
    Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.primary) {
        Column(
            Modifier.fillMaxSize().padding(32.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                stringResource(R.string.app_name),
                style = MaterialTheme.typography.displaySmall,
                color = MaterialTheme.colorScheme.onPrimary,
                textAlign = TextAlign.Center,
                modifier = Modifier.semantics { heading() }
            )
            Spacer(Modifier.height(12.dp))
            Text(
                stringResource(R.string.home_tagline),
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onPrimary,
                textAlign = TextAlign.Center
            )
            Spacer(Modifier.height(40.dp))
            Text(
                stringResource(R.string.splash_credit),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onPrimary,
                textAlign = TextAlign.Center
            )
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
    question: String, answer: String?, limitation: String?, citations: List<String>,
    mode: ResponseMode?, isBusy: Boolean, error: String?, modelLoaded: Boolean,
    style: TutorStyle, onToggleStyle: () -> Unit,
    topics: List<TopicSummary>, recommendedId: String?,
    onQuestionChange: (String) -> Unit, onAsk: () -> Unit, onCancel: () -> Unit, onStartTopic: (String) -> Unit
) {
    LazyColumn(
        Modifier.fillMaxSize().imePadding().padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item { ScreenHeading(stringResource(R.string.tutor_title)) }
        item { Text(stringResource(R.string.tutor_intro)) }
        if (!modelLoaded) {
            item {
                Text(
                    stringResource(R.string.tutor_no_model_hint),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
        item {
            OutlinedButton(onClick = onToggleStyle, modifier = Modifier.fillMaxWidth()) {
                Text(
                    stringResource(
                        if (style == TutorStyle.SOCRATIC) R.string.tutor_style_socratic
                        else R.string.tutor_style_direct
                    )
                )
            }
        }
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
            val structured = StructuredAnswer.parse(text)
            if (structured.isStructured) {
                val lead = structured.answer ?: structured.preamble
                if (lead.isNotBlank()) item { Text(lead) }
                if (structured.steps.isNotEmpty()) {
                    item { Text(stringResource(R.string.tutor_steps), style = MaterialTheme.typography.titleSmall) }
                    items(structured.steps) { step -> Text(stringResource(R.string.tutor_step_line, step)) }
                }
                structured.check?.let { check ->
                    item { Text(stringResource(R.string.tutor_check), style = MaterialTheme.typography.titleSmall) }
                    item { Text(check) }
                }
            } else {
                item { Text(text) }
            }
            limitation?.let { l ->
                item { Text(l, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            }
            mode?.let { m ->
                item {
                    val label = when (m) {
                        ResponseMode.LOCAL_MODEL -> R.string.tutor_mode_local
                        ResponseMode.OFFLINE_FALLBACK -> R.string.tutor_mode_offline
                        ResponseMode.DETERMINISTIC -> R.string.tutor_mode_deterministic
                    }
                    Text(
                        stringResource(label),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
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
private fun levelLabel(level: LearnerLevel): String = stringResource(
    when (level) {
        LearnerLevel.SCHOOL -> R.string.level_school
        LearnerLevel.BACHELOR -> R.string.level_bachelor
        LearnerLevel.MASTER -> R.string.level_master
        LearnerLevel.UNKNOWN -> R.string.level_unknown
    }
)

@Composable
private fun SettingsScreen(
    message: String?,
    modelState: ModelState,
    catalog: List<ModelManifest>,
    deviceTier: RamTier,
    onDownloadModel: (String) -> Unit,
    onImportModel: (android.net.Uri) -> Unit,
    onLoadModel: () -> Unit,
    onUnloadModel: () -> Unit,
    onDeleteModel: () -> Unit,
    onCancelModel: () -> Unit,
    onExport: (android.net.Uri) -> Unit,
    onDeleteAll: () -> Unit,
    profile: LearnerProfile,
    onLevelChange: (LearnerLevel) -> Unit,
    onStyleChange: (TutorStyle) -> Unit,
    onLanguageChange: (String) -> Unit,
    metrics: RuntimeMetrics?,
    freeStorageBytes: Long
) {
    var confirmDeleteAll by remember { mutableStateOf(false) }
    var confirmDeleteModel by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val exporter = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri -> uri?.let(onExport) }
    val importer = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> uri?.let(onImportModel) }

    val busy = modelState is ModelState.Downloading || modelState is ModelState.Verifying ||
        modelState is ModelState.Importing || modelState is ModelState.Loading
    val ready = modelState as? ModelState.Ready
    val failed = modelState as? ModelState.Failed
    val recommended = catalog.filter { it.supports(deviceTier) }.maxByOrNull { it.minimumTier.rank }
    val live = Modifier.semantics { liveRegion = LiveRegionMode.Polite }

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        ScreenHeading(stringResource(R.string.settings_title))
        Text(stringResource(R.string.settings_intro))

        Text(stringResource(R.string.settings_profile_heading), style = MaterialTheme.typography.titleMedium)
        Text(stringResource(R.string.settings_profile_intro), style = MaterialTheme.typography.bodySmall)
        Text(stringResource(R.string.settings_level), style = MaterialTheme.typography.labelMedium)
        Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            LearnerLevel.entries.forEach { level ->
                FilterChip(
                    selected = profile.level == level,
                    onClick = { onLevelChange(level) },
                    label = { Text(levelLabel(level)) }
                )
            }
        }
        Text(stringResource(R.string.settings_style), style = MaterialTheme.typography.labelMedium)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(
                selected = profile.style == TutorStyle.DIRECT,
                onClick = { onStyleChange(TutorStyle.DIRECT) },
                label = { Text(stringResource(R.string.tutor_style_direct)) }
            )
            FilterChip(
                selected = profile.style == TutorStyle.SOCRATIC,
                onClick = { onStyleChange(TutorStyle.SOCRATIC) },
                label = { Text(stringResource(R.string.tutor_style_socratic)) }
            )
        }
        Text(stringResource(R.string.settings_language), style = MaterialTheme.typography.labelMedium)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(
                selected = profile.language == "en",
                onClick = { onLanguageChange("en") },
                label = { Text(stringResource(R.string.language_english)) }
            )
            FilterChip(
                selected = profile.language == "ne",
                onClick = { onLanguageChange("ne") },
                label = { Text(stringResource(R.string.language_nepali)) }
            )
        }

        Text(stringResource(R.string.settings_model_heading), style = MaterialTheme.typography.titleMedium)
        Text(stringResource(R.string.settings_model_intro), style = MaterialTheme.typography.bodySmall)
        Text(
            stringResource(R.string.settings_model_device, deviceTier.label),
            style = MaterialTheme.typography.bodySmall
        )
        Text(
            stringResource(R.string.settings_model_privacy),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )

        when (modelState) {
            ModelState.NotInstalled -> Text(stringResource(R.string.settings_model_none))
            ModelState.Importing -> {
                Text(stringResource(R.string.settings_model_importing), modifier = live)
                CircularProgressIndicator()
            }
            is ModelState.Downloading -> {
                val fraction = if (modelState.total > 0) {
                    (modelState.bytes.toFloat() / modelState.total.toFloat()).coerceIn(0f, 1f)
                } else 0f
                Text(
                    stringResource(
                        R.string.settings_model_downloading,
                        Formatter.formatShortFileSize(context, modelState.bytes),
                        Formatter.formatShortFileSize(context, modelState.total)
                    ),
                    modifier = live
                )
                LinearProgressIndicator(progress = { fraction }, modifier = Modifier.fillMaxWidth())
            }
            is ModelState.Verifying -> {
                Text(stringResource(R.string.settings_model_verifying), modifier = live)
                CircularProgressIndicator()
            }
            is ModelState.Loading -> {
                Text(stringResource(R.string.settings_model_loading), modifier = live)
                CircularProgressIndicator()
            }
            is ModelState.Ready -> Text(
                if (modelState.loaded) {
                    stringResource(R.string.settings_model_ready_loaded, modelState.manifest.displayName)
                } else {
                    stringResource(R.string.settings_model_ready_unloaded, modelState.manifest.displayName)
                },
                modifier = live
            )
            is ModelState.Failed -> Text(
                stringResource(R.string.settings_model_failed, modelState.message),
                color = MaterialTheme.colorScheme.error,
                modifier = live
            )
        }

        catalog.forEach { manifest ->
            val isInstalled = ready?.manifest?.id == manifest.id || failed?.manifest?.id == manifest.id
            val isDownloading = (modelState as? ModelState.Downloading)?.manifest?.id == manifest.id
            val loaded = ready?.manifest?.id == manifest.id && ready.loaded
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(manifest.displayName, style = MaterialTheme.typography.titleSmall)
                if (manifest.id == recommended?.id) {
                    Text(
                        stringResource(R.string.settings_model_recommended),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary
                    )
                }
                Text(
                    stringResource(
                        R.string.settings_model_details,
                        manifest.quantization,
                        Formatter.formatShortFileSize(context, manifest.sizeBytes)
                    ),
                    style = MaterialTheme.typography.bodySmall
                )
                Text(
                    stringResource(R.string.settings_model_meta, manifest.minimumTier.label, manifest.license),
                    style = MaterialTheme.typography.bodySmall
                )
                if (!manifest.supports(deviceTier)) {
                    Text(
                        stringResource(R.string.settings_model_unsupported),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error
                    )
                }
                when {
                    isDownloading -> OutlinedButton(onClick = onCancelModel, modifier = Modifier.fillMaxWidth()) {
                        Text(stringResource(R.string.settings_model_cancel))
                    }
                    loaded -> Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = onUnloadModel) { Text(stringResource(R.string.settings_model_unload)) }
                        OutlinedButton(onClick = { confirmDeleteModel = true }) { Text(stringResource(R.string.settings_model_delete)) }
                    }
                    ready?.manifest?.id == manifest.id -> Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = onLoadModel) { Text(stringResource(R.string.settings_model_load)) }
                        OutlinedButton(onClick = { confirmDeleteModel = true }) { Text(stringResource(R.string.settings_model_delete)) }
                    }
                    isInstalled -> OutlinedButton(onClick = { confirmDeleteModel = true }, modifier = Modifier.fillMaxWidth()) {
                        Text(stringResource(R.string.settings_model_delete))
                    }
                    else -> Button(
                        onClick = { onDownloadModel(manifest.id) },
                        enabled = manifest.supports(deviceTier) && !busy,
                        modifier = Modifier.fillMaxWidth()
                    ) { Text(stringResource(R.string.settings_model_download)) }
                }
            }
        }

        OutlinedButton(
            onClick = { importer.launch(arrayOf("application/octet-stream", "*/*")) },
            enabled = !busy,
            modifier = Modifier.fillMaxWidth()
        ) { Text(stringResource(R.string.settings_model_import)) }
        Text(
            stringResource(R.string.settings_model_import_hint),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )

        Text(stringResource(R.string.settings_diagnostics), style = MaterialTheme.typography.titleMedium)
        if (metrics == null) {
            Text(stringResource(R.string.settings_diagnostics_empty), style = MaterialTheme.typography.bodySmall)
        } else {
            Text(stringResource(R.string.settings_diag_backend, metrics.backend), style = MaterialTheme.typography.bodySmall)
            metrics.loadMillis?.let {
                Text(stringResource(R.string.settings_diag_load, it), style = MaterialTheme.typography.bodySmall)
            }
            metrics.firstTokenMillis?.let {
                Text(stringResource(R.string.settings_diag_first_token, it), style = MaterialTheme.typography.bodySmall)
            }
            metrics.tokensPerSecond?.let { speed ->
                Text(
                    stringResource(R.string.settings_diag_speed, speed.toInt(), metrics.estimatedTokens),
                    style = MaterialTheme.typography.bodySmall
                )
            }
            metrics.heapUsedMb?.let {
                Text(stringResource(R.string.settings_diag_heap, it), style = MaterialTheme.typography.bodySmall)
            }
        }
        Text(
            stringResource(
                R.string.settings_diag_storage,
                Formatter.formatShortFileSize(context, freeStorageBytes)
            ),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )

        OutlinedButton(onClick = { exporter.launch("ashura-tutor-export.json") }, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.settings_export))
        }
        message?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
        OutlinedButton(onClick = { confirmDeleteAll = true }, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.settings_delete_all))
        }
        Text(
            stringResource(R.string.splash_credit),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp)
        )
    }
    if (confirmDeleteAll) {
        AlertDialog(
            onDismissRequest = { confirmDeleteAll = false },
            title = { Text(stringResource(R.string.settings_delete_title)) },
            text = { Text(stringResource(R.string.settings_delete_body)) },
            confirmButton = { TextButton(onClick = { confirmDeleteAll = false; onDeleteAll() }) { Text(stringResource(R.string.action_delete)) } },
            dismissButton = { TextButton(onClick = { confirmDeleteAll = false }) { Text(stringResource(R.string.action_cancel)) } }
        )
    }
    if (confirmDeleteModel) {
        val name = (ready?.manifest ?: failed?.manifest)?.displayName ?: stringResource(R.string.settings_model_heading)
        AlertDialog(
            onDismissRequest = { confirmDeleteModel = false },
            title = { Text(stringResource(R.string.settings_model_delete_title)) },
            text = { Text(stringResource(R.string.settings_model_delete_body, name)) },
            confirmButton = { TextButton(onClick = { confirmDeleteModel = false; onDeleteModel() }) { Text(stringResource(R.string.action_delete)) } },
            dismissButton = { TextButton(onClick = { confirmDeleteModel = false }) { Text(stringResource(R.string.action_cancel)) } }
        )
    }
}
