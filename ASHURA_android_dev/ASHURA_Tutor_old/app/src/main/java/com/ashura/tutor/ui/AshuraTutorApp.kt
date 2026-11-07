package com.ashura.tutor.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Book
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Insights
import androidx.compose.material.icons.filled.School
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import com.ashura.tutor.domain.Lesson
import com.ashura.tutor.domain.LearnerLevel
import com.ashura.tutor.domain.PracticeQuestion
import com.ashura.tutor.domain.ReviewOutcome

private enum class Destination(val label: String, val icon: ImageVector) {
    HOME("Home", Icons.Default.Home), TUTOR("Tutor", Icons.Default.School),
    LIBRARY("Library", Icons.Default.Book), PROGRESS("Progress", Icons.Default.Insights),
    SETTINGS("Settings", Icons.Default.Settings)
}

@Composable
fun AshuraTutorApp(viewModel: TutorViewModel) {
    var selected by rememberSaveable { mutableStateOf(Destination.HOME.name) }
    val state by viewModel.state.collectAsState()
    val lesson by viewModel.lesson.collectAsState()

    var practiceQuestion by rememberSaveable { mutableStateOf<PracticeQuestion?>(null) }

    Scaffold(
        bottomBar = {
            NavigationBar {
                Destination.entries.forEach { item ->
                    NavigationBarItem(
                        selected = selected == item.name,
                        onClick = { selected = item.name; practiceQuestion = null },
                        icon = { Icon(item.icon, contentDescription = item.label) },
                        label = { Text(item.label) }
                    )
                }
            }
        }
    ) { insets ->
        Surface(Modifier.fillMaxSize().padding(insets), color = MaterialTheme.colorScheme.background) {
            when (Destination.valueOf(selected)) {
                Destination.HOME -> HomeScreen { selected = Destination.TUTOR.name }
                Destination.TUTOR -> {
                    if (practiceQuestion != null) {
                        PracticeScreen(
                            question = practiceQuestion!!,
                            onRecord = { answer, outcome ->
                                viewModel.recordPractice(
                                    conceptId = practiceQuestion!!.conceptId,
                                    outcome = outcome,
                                    currentMastery = 0.0,
                                    currentIntervalDays = 1
                                )
                                practiceQuestion = null
                            },
                            onNavigateHome = { practiceQuestion = null }
                        )
                    } else if (lesson != null) {
                        LessonScreen(
                            lesson = lesson,
                            onStartPractice = { question ->
                                practiceQuestion = question
                            },
                            onNavigateHome = { viewModel.clearLesson() }
                        )
                    } else {
                        TutorScreen(
                            question = state.question,
                            answer = state.answer,
                            isBusy = state.isBusy,
                            error = state.error,
                            onQuestionChange = viewModel::updateQuestion,
                            onAsk = viewModel::ask,
                            onStartLesson = {
                                viewModel.startLesson(subject = "Mathematics", topic = "Arithmetic", level = LearnerLevel.SCHOOL)
                            },
                            onPractice = null
                        )
                    }
                }
                Destination.LIBRARY -> InfoScreen(
                    "Your Library",
                    "Study material is designed to stay on this device. Text-note storage and search exist in the data layer; document picker and file parsers are not yet integrated."
                )
                Destination.PROGRESS -> InfoScreen(
                    "Your Progress",
                    "Study events are stored locally. Mastery dashboards and spaced-repetition scheduling are not enabled yet."
                )
                Destination.SETTINGS -> InfoScreen(
                    "Settings",
                    "No account, analytics, advertising, API key, or mandatory cloud service is included. Local model controls will arrive with runtime integration."
                )
            }
        }
    }
}

@Composable
private fun HomeScreen(onStart: () -> Unit) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text("ASHURA Tutor", style = MaterialTheme.typography.headlineLarge)
        Text("Learn with understanding, not memorisation.", style = MaterialTheme.typography.titleMedium)
        Text("An offline-first study space. Your notes and study history stay on this device.")
        Button(onClick = onStart, modifier = Modifier.fillMaxWidth()) { Text("Start learning") }
        Text("Designed to work without an account or API key.")
    }
}

@Composable
private fun TutorScreen(
    question: String, answer: String?, isBusy: Boolean, error: String?,
    onQuestionChange: (String) -> Unit, onAsk: () -> Unit,
    onStartLesson: () -> Unit, onPractice: (() -> Unit)?
) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("Tutor", style = MaterialTheme.typography.headlineMedium)
        Text("This build handles exact basic arithmetic and provides an honest offline study scaffold.")
        OutlinedTextField(
            value = question, onValueChange = onQuestionChange, modifier = Modifier.fillMaxWidth(),
            label = { Text("What would you like to understand?") }, minLines = 3
        )
        androidx.compose.foundation.layout.Spacer(modifier = Modifier.height(8.dp))
        Button(onClick = onAsk, enabled = !isBusy && question.isNotBlank()) {
            Text(if (isBusy) "Working…" else "Ask")
        }
        if (isBusy) CircularProgressIndicator()
        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        answer?.let {
            androidx.compose.foundation.layout.Spacer(modifier = Modifier.height(12.dp))
            Text("Response", style = MaterialTheme.typography.titleLarge)
            Text(it)
        }
        androidx.compose.foundation.layout.Spacer(modifier = Modifier.height(20.dp))
        Button(onClick = onStartLesson, modifier = Modifier.fillMaxWidth()) {
            Text(text = "Start a lesson")
        }
    }
}

private val lessonHasPractice: Boolean
    get() = false

@Composable
private fun InfoScreen(title: String, description: String) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text(title, style = MaterialTheme.typography.headlineMedium)
        Text(description)
    }
}
