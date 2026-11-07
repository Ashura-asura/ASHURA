package com.ashura.tutor.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import com.ashura.tutor.R
import com.ashura.tutor.domain.ReviewOutcome
import com.ashura.tutor.domain.assessment.Verdict

@Composable
@OptIn(ExperimentalMaterial3Api::class)
fun PracticeScreen(
    state: PracticeUiState,
    onSubmit: (String) -> Unit,
    onSelfAssess: (ReviewOutcome) -> Unit,
    onHint: () -> Unit,
    onShowSolution: () -> Unit,
    onNext: () -> Unit,
    onClose: () -> Unit
) {
    val question = state.question ?: return
    var answer by rememberSaveable(question.id) { mutableStateOf("") }
    var selfOutcome by rememberSaveable(question.id) { mutableStateOf<String?>(null) }
    val done = state.finished

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.practice_title)) },
                navigationIcon = {
                    IconButton(onClick = onClose) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = stringResource(R.string.action_back_to_lesson))
                    }
                }
            )
        }
    ) { paddingValues ->
        LazyColumn(
            Modifier.fillMaxSize().padding(paddingValues).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            item { Text(question.prompt, style = MaterialTheme.typography.titleLarge) }

            if (question.selfAssessed) {
                item {
                    OutlinedTextField(
                        value = answer, onValueChange = { answer = it }, enabled = !done,
                        label = { Text(stringResource(R.string.practice_your_answer_review)) },
                        modifier = Modifier.fillMaxWidth(), minLines = 3
                    )
                }
                item {
                    Text(stringResource(R.string.practice_self_assess_hint), style = MaterialTheme.typography.bodySmall)
                }
                items(ReviewOutcome.entries.size) { index ->
                    val outcome = ReviewOutcome.entries[index]
                    Row(
                        Modifier.fillMaxWidth().selectable(
                            selected = selfOutcome == outcome.name, enabled = !done, role = Role.RadioButton,
                            onClick = { selfOutcome = outcome.name }
                        ),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        RadioButton(selected = selfOutcome == outcome.name, onClick = null, enabled = !done)
                        Text(stringResource(outcome.labelRes()))
                    }
                }
                item {
                    Button(
                        onClick = { selfOutcome?.let { onSelfAssess(ReviewOutcome.valueOf(it)) } },
                        enabled = selfOutcome != null && !done && !state.busy, modifier = Modifier.fillMaxWidth()
                    ) { Text(stringResource(R.string.practice_record)) }
                }
            } else {
                item {
                    OutlinedTextField(
                        value = answer, onValueChange = { answer = it }, enabled = !done,
                        label = { Text(stringResource(R.string.practice_your_answer)) },
                        singleLine = true, modifier = Modifier.fillMaxWidth(),
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                        keyboardActions = KeyboardActions(onDone = {
                            if (answer.isNotBlank() && !done && !state.busy) onSubmit(answer)
                        })
                    )
                }
                item {
                    Button(
                        onClick = { onSubmit(answer) },
                        enabled = answer.isNotBlank() && !done && !state.busy, modifier = Modifier.fillMaxWidth()
                    ) {
                        Text(stringResource(if (state.busy) R.string.practice_checking else R.string.practice_check))
                    }
                }
                if (!done) {
                    item {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedButton(onClick = onHint, enabled = state.hintsShown < question.hints.size) {
                                Text(stringResource(R.string.practice_hint, state.hintsShown, question.hints.size))
                            }
                            OutlinedButton(onClick = onShowSolution, enabled = !state.solutionShown) {
                                Text(stringResource(R.string.practice_show_solution))
                            }
                        }
                    }
                }
                items(state.hintsShown) { index ->
                    Text(stringResource(R.string.practice_hint_n, index + 1, question.hints[index]))
                }
                if (state.solutionShown) {
                    item {
                        Text(
                            stringResource(R.string.practice_answer, question.expectedAnswer),
                            style = MaterialTheme.typography.titleMedium
                        )
                    }
                    question.explanation?.let { explanation -> item { Text(explanation) } }
                    item {
                        Text(
                            stringResource(R.string.practice_solution_note),
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }
            }

            state.check?.let { check ->
                item {
                    Text(
                        check.feedback,
                        modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
                        color = if (check.verdict == Verdict.CORRECT) MaterialTheme.colorScheme.primary
                        else MaterialTheme.colorScheme.error
                    )
                }
            }
            state.error?.let { error -> item { Text(error, color = MaterialTheme.colorScheme.error) } }
            state.schedule?.let { schedule ->
                item {
                    Text(
                        pluralStringResource(
                            R.plurals.practice_schedule,
                            schedule.nextIntervalDays,
                            (schedule.masteryEstimate * 100).toInt(),
                            schedule.nextIntervalDays
                        ),
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }
            if (done && state.remaining > 0) {
                item {
                    Button(onClick = onNext, modifier = Modifier.fillMaxWidth()) {
                        Text(pluralStringResource(R.plurals.practice_next, state.remaining, state.remaining))
                    }
                }
            } else if (done) {
                item {
                    Button(onClick = onClose, modifier = Modifier.fillMaxWidth()) {
                        Text(stringResource(R.string.practice_done))
                    }
                }
            }
        }
    }
}

private fun ReviewOutcome.labelRes(): Int = when (this) {
    ReviewOutcome.INCORRECT -> R.string.review_incorrect
    ReviewOutcome.CORRECT_WITH_HELP -> R.string.review_correct_with_help
    ReviewOutcome.CORRECT_INDEPENDENTLY -> R.string.review_correct_independently
}
