package com.ashura.tutor.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
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
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.ashura.tutor.R
import com.ashura.tutor.domain.Lesson
import com.ashura.tutor.domain.PracticeQuestion

@Composable
@OptIn(ExperimentalMaterial3Api::class)
fun LessonScreen(
    lesson: Lesson?,
    onStartPractice: (PracticeQuestion) -> Unit,
    onNavigateHome: () -> Unit
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        if (lesson == null) stringResource(R.string.lesson_none_title)
                        else stringResource(R.string.lesson_title_format, lesson.subject, lesson.topic),
                        maxLines = 1, overflow = TextOverflow.Ellipsis
                    )
                },
                navigationIcon = {
                    IconButton(onClick = onNavigateHome) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = stringResource(R.string.action_back_to_tutor))
                    }
                }
            )
        }
    ) { paddingValues ->
        if (lesson == null) {
            LazyColumn(
                Modifier.fillMaxSize().padding(paddingValues).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                item { Text(stringResource(R.string.lesson_open_hint)) }
                item {
                    Button(onClick = onNavigateHome, modifier = Modifier.fillMaxWidth()) {
                        Text(stringResource(R.string.lesson_back))
                    }
                }
            }
            return@Scaffold
        }

        LazyColumn(
            Modifier.fillMaxSize().padding(paddingValues).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            item { ScreenHeading(lesson.topic) }
            if (lesson.isGenericScaffold) {
                item { Text(stringResource(R.string.lesson_generic_warning), color = MaterialTheme.colorScheme.error) }
            }

            item { SectionHeading(stringResource(R.string.lesson_objectives)) }
            items(lesson.objectives) { Text(stringResource(R.string.lesson_bullet, it)) }

            if (lesson.keyVocabulary.isNotEmpty()) {
                item { SectionHeading(stringResource(R.string.lesson_key_words)) }
                items(lesson.keyVocabulary) { Text(stringResource(R.string.lesson_bullet, it)) }
            }

            item { SectionHeading(stringResource(R.string.lesson_outline)) }
            items(lesson.explanationOutline) { Text(stringResource(R.string.lesson_bullet, it)) }

            lesson.workedExample?.takeIf { it.isNotBlank() }?.let { example ->
                item { SectionHeading(stringResource(R.string.lesson_worked_example)) }
                item { Text(example) }
            }

            if (lesson.misconceptions.isNotEmpty()) {
                item { SectionHeading(stringResource(R.string.lesson_common_mistakes)) }
                items(lesson.misconceptions) { Text(stringResource(R.string.lesson_bullet, it)) }
            }

            item { SectionHeading(stringResource(R.string.lesson_practice)) }
            items(lesson.practiceQuestions, key = { it.id }) { question ->
                Button(onClick = { onStartPractice(question) }, modifier = Modifier.fillMaxWidth()) {
                    Text(question.prompt)
                }
            }

            if (lesson.sourceRefs.isNotEmpty()) {
                item {
                    Text(
                        stringResource(R.string.lesson_source, lesson.sourceRefs.joinToString()),
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }
        }
    }
}
