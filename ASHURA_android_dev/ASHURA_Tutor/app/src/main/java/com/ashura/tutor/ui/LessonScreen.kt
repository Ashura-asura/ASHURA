package com.ashura.tutor.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.School
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.ashura.tutor.domain.Lesson
import com.ashura.tutor.domain.PracticeQuestion

@Composable
@OptIn(ExperimentalMaterial3Api::class)
fun LessonScreen(
    lesson: Lesson?,
    onStartPractice: (PracticeQuestion) -> Unit,
    onNavigateHome: () -> Unit
) {
    if (lesson == null) {
        EmptyState("No lesson selected", "Open a topic to begin a lesson.", onNavigateHome)
        return
    }
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("${lesson.subject} · ${lesson.topic}") },
                navigationIcon = {
                    IconButton(onClick = onNavigateHome) {
                        Icon(imageVector = Icons.Filled.School, contentDescription = null)
                    }
                }
            )
        }
    ) { paddingValues ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .padding(16.dp)
                .verticalScroll(rememberScrollState())
        ) {
            Text(lesson.topic, style = MaterialTheme.typography.headlineMedium)
            Text(lesson.subject, style = MaterialTheme.typography.titleMedium)
            androidx.compose.foundation.layout.Spacer(modifier = Modifier.height(16.dp))
            Text("Objectives", style = MaterialTheme.typography.titleLarge)
            lesson.objectives.forEach { objective ->
                Text(text = "• $objective")
                androidx.compose.foundation.layout.Spacer(modifier = Modifier.height(4.dp))
            }
            androidx.compose.foundation.layout.Spacer(modifier = Modifier.height(16.dp))
            Text("Outline", style = MaterialTheme.typography.titleLarge)
            lesson.explanationOutline.forEach { step ->
                Text(text = "• $step")
                androidx.compose.foundation.layout.Spacer(modifier = Modifier.height(4.dp))
            }
            lesson.workedExample?.takeIf { it.isNotBlank() }?.let {
                androidx.compose.foundation.layout.Spacer(modifier = Modifier.height(16.dp))
                Text("Worked example", style = MaterialTheme.typography.titleLarge)
                androidx.compose.foundation.layout.Spacer(modifier = Modifier.height(8.dp))
                Text(it)
            }
            androidx.compose.foundation.layout.Spacer(modifier = Modifier.height(16.dp))
            Text("Practice", style = MaterialTheme.typography.titleLarge)
            lesson.practiceQuestions.forEach { question ->
                Button(
                    onClick = { onStartPractice(question) },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(text = question.prompt)
                }
                androidx.compose.foundation.layout.Spacer(modifier = Modifier.height(8.dp))
            }
        }
    }
}

@Composable
@OptIn(ExperimentalMaterial3Api::class)
private fun EmptyState(title: String, description: String, onNavigateHome: () -> Unit) {
    Scaffold(
        topBar = {
            TopAppBar(title = { Text(title) }, navigationIcon = {
                IconButton(onClick = onNavigateHome) {
                    Icon(
                        imageVector = Icons.Filled.ArrowBack,
                        contentDescription = null
                    )
                }
            })
        }
    ) { paddingValues ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .padding(24.dp)
                .verticalScroll(rememberScrollState())
        ) {
            Text(title, style = MaterialTheme.typography.headlineMedium)
            androidx.compose.foundation.layout.Spacer(modifier = Modifier.height(16.dp))
            Text(description)
            androidx.compose.foundation.layout.Spacer(modifier = Modifier.height(24.dp))
            Button(onClick = onNavigateHome, modifier = Modifier.fillMaxWidth()) {
                Text(text = "Home")
            }
        }
    }
}
