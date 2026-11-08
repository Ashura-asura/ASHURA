package com.ashura.tutor.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.selection.selectable
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.ashura.tutor.R
import com.ashura.tutor.domain.assessment.TestMode
import com.ashura.tutor.domain.assessment.TestSession
import com.ashura.tutor.domain.assessment.formatClock

@Composable
internal fun testModeLabel(mode: TestMode): String = stringResource(
    when (mode) {
        TestMode.QUICK -> R.string.test_mode_quick
        TestMode.MEDIUM -> R.string.test_mode_medium
        TestMode.LONG -> R.string.test_mode_long
    }
)

/**
 * Timed four-option test: one question at a time, free navigation, an automatic countdown and a
 * result summary with marks, time taken and the change from the previous test of the same mode.
 */
@Composable
@OptIn(ExperimentalMaterial3Api::class)
fun TestScreen(
    state: TestUiState,
    onSelect: (Int) -> Unit,
    onNext: () -> Unit,
    onPrevious: () -> Unit,
    onFinish: () -> Unit,
    onClose: () -> Unit,
    onRetake: () -> Unit
) {
    val session = state.session ?: return
    var confirmExit by remember { mutableStateOf(false) }

    BackHandler {
        if (session.isFinished) onClose() else confirmExit = true
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(
                            if (session.isFinished) stringResource(R.string.test_result_title)
                            else testModeLabel(session.mode)
                        )
                        Text(
                            session.title,
                            style = MaterialTheme.typography.labelSmall,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                },
                navigationIcon = {
                    IconButton(onClick = { if (session.isFinished) onClose() else confirmExit = true }) {
                        Icon(Icons.Default.Close, contentDescription = stringResource(R.string.test_close))
                    }
                },
                actions = {
                    if (!session.isFinished) {
                        Text(
                            formatClock(state.remainingSeconds),
                            style = MaterialTheme.typography.titleMedium,
                            color = if (state.remainingSeconds <= 60) MaterialTheme.colorScheme.error
                            else MaterialTheme.colorScheme.onSurface,
                            modifier = Modifier.padding(end = 16.dp)
                        )
                    }
                }
            )
        }
    ) { insets ->
        if (session.isFinished) {
            TestResult(
                state = state,
                session = session,
                onClose = onClose,
                onRetake = onRetake,
                modifier = Modifier.fillMaxSize().padding(insets)
            )
        } else {
            TestQuestion(
                state = state,
                session = session,
                onSelect = onSelect,
                onNext = onNext,
                onPrevious = onPrevious,
                onFinish = onFinish,
                modifier = Modifier.fillMaxSize().padding(insets)
            )
        }
    }

    if (confirmExit) {
        AlertDialog(
            onDismissRequest = { confirmExit = false },
            title = { Text(stringResource(R.string.test_exit_title)) },
            text = { Text(stringResource(R.string.test_exit_body)) },
            confirmButton = {
                TextButton(onClick = { confirmExit = false; onClose() }) {
                    Text(stringResource(R.string.test_exit_confirm))
                }
            },
            dismissButton = {
                TextButton(onClick = { confirmExit = false }) { Text(stringResource(R.string.action_cancel)) }
            }
        )
    }
}

@Composable
private fun TestQuestion(
    state: TestUiState,
    session: TestSession,
    onSelect: (Int) -> Unit,
    onNext: () -> Unit,
    onPrevious: () -> Unit,
    onFinish: () -> Unit,
    modifier: Modifier = Modifier
) {
    val question = session.questions[session.currentIndex]
    val chosen = session.answerAt(session.currentIndex)
    LazyColumn(
        modifier.padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item {
            Text(
                stringResource(R.string.test_question_counter, session.currentIndex + 1, session.total),
                style = MaterialTheme.typography.labelLarge
            )
        }
        item {
            LinearProgressIndicator(
                progress = { (session.currentIndex + 1).toFloat() / session.total },
                modifier = Modifier.fillMaxWidth()
            )
        }
        item {
            Text(question.prompt, style = MaterialTheme.typography.titleLarge)
        }
        itemsIndexed(question.options) { index, option ->
            Row(
                Modifier
                    .fillMaxWidth()
                    .heightIn(min = 56.dp)
                    .selectable(
                        selected = chosen == index,
                        role = Role.RadioButton,
                        onClick = { onSelect(index) }
                    )
                    .padding(vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                RadioButton(selected = chosen == index, onClick = null)
                Text(option, style = MaterialTheme.typography.bodyLarge)
            }
        }
        item {
            Text(
                stringResource(R.string.test_answered_count, session.answeredCount, session.total),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(
                    onClick = onPrevious,
                    enabled = session.currentIndex > 0,
                    modifier = Modifier.weight(1f)
                ) { Text(stringResource(R.string.test_previous)) }
                if (session.currentIndex == session.total - 1) {
                    Button(onClick = onFinish, modifier = Modifier.weight(1f)) {
                        Text(stringResource(R.string.test_finish))
                    }
                } else {
                    Button(onClick = onNext, modifier = Modifier.weight(1f)) {
                        Text(stringResource(R.string.test_next))
                    }
                }
            }
        }
        state.error?.let { item { Text(it, color = MaterialTheme.colorScheme.error) } }
    }
}

@Composable
private fun TestResult(
    state: TestUiState,
    session: TestSession,
    onClose: () -> Unit,
    onRetake: () -> Unit,
    modifier: Modifier = Modifier
) {
    LazyColumn(
        modifier.padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item {
            Text(
                stringResource(R.string.test_result_marks, session.correctCount, session.total),
                style = MaterialTheme.typography.displaySmall
            )
        }
        item {
            Text(
                stringResource(R.string.test_result_percent, session.scorePercent),
                style = MaterialTheme.typography.titleLarge
            )
        }
        item {
            Text(
                stringResource(R.string.test_result_time, formatClock(session.timeTakenSeconds)),
                style = MaterialTheme.typography.bodyLarge
            )
        }
        if (session.timedOut) {
            item {
                Text(
                    stringResource(R.string.test_result_timed_out, session.unansweredCount),
                    color = MaterialTheme.colorScheme.error
                )
            }
        }
        item {
            HorizontalDivider()
        }
        item {
            when {
                state.saving -> Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    CircularProgressIndicator()
                    Text(stringResource(R.string.test_result_saving))
                }
                state.resultIsFirstInMode -> Text(stringResource(R.string.test_result_first, testModeLabel(session.mode)))
                state.resultDeltaMarks != null -> Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(
                        stringResource(
                            R.string.test_result_delta_marks,
                            signed(state.resultDeltaMarks),
                            testModeLabel(session.mode)
                        )
                    )
                    state.resultDeltaPercent?.let {
                        Text(
                            stringResource(R.string.test_result_delta_percent, signed(it)),
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }
            }
        }
        state.error?.let { item { Text(it, color = MaterialTheme.colorScheme.error) } }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = onRetake, modifier = Modifier.weight(1f)) {
                    Text(stringResource(R.string.test_retake))
                }
                Button(onClick = onClose, modifier = Modifier.weight(1f)) {
                    Text(stringResource(R.string.test_done))
                }
            }
        }
        item { SectionHeading(stringResource(R.string.test_review_title)) }
        itemsIndexed(session.questions) { index, question ->
            val answer = session.answerAt(index)
            val correct = answer == question.correctIndex
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(
                    "${index + 1}. ${question.prompt}",
                    style = MaterialTheme.typography.titleSmall,
                    maxLines = 3,
                    overflow = TextOverflow.Ellipsis
                )
                Text(
                    if (answer == null) stringResource(R.string.test_review_unanswered)
                    else stringResource(R.string.test_review_your_answer, question.options[answer]),
                    color = if (correct) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error
                )
                Text(
                    stringResource(R.string.test_review_correct, question.options[question.correctIndex]),
                    style = MaterialTheme.typography.bodySmall
                )
                Text(
                    stringResource(R.string.test_review_source, question.sourceTitle),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                if (index < session.questions.lastIndex) HorizontalDivider()
            }
        }
    }
}

private fun signed(value: Int): String = if (value > 0) "+$value" else "$value"
