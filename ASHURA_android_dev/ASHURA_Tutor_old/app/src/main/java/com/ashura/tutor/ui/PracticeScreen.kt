package com.ashura.tutor.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.filled.Assessment
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.ashura.tutor.domain.PracticeQuestion
import com.ashura.tutor.domain.ReviewOutcome

@Composable
@OptIn(ExperimentalMaterial3Api::class)
fun PracticeScreen(
    question: PracticeQuestion,
    onRecord: (String, ReviewOutcome) -> Unit,
    onNavigateHome: () -> Unit
) {
    var answer by remember { mutableStateOf("") }
    var selectedOutcome by remember { mutableStateOf<ReviewOutcome?>(null) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Practice") },
                navigationIcon = {
                    IconButton(onClick = onNavigateHome) {
                        Icon(imageVector = Assessment, contentDescription = null)
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
            Text("Practice", style = MaterialTheme.typography.headlineMedium)
            androidx.compose.foundation.layout.Spacer(modifier = Modifier.height(16.dp))
            Text(question.prompt, style = MaterialTheme.typography.titleLarge)
            androidx.compose.foundation.layout.Spacer(modifier = Modifier.height(16.dp))
            OutlinedTextField(
                value = answer,
                onValueChange = { answer = it },
                label = { Text(text = "Your answer") },
                modifier = Modifier.fillMaxWidth(),
                minLines = 3
            )
            androidx.compose.foundation.layout.Spacer(modifier = Modifier.height(16.dp))
            Text("How did you go?", style = MaterialTheme.typography.titleMedium)
            androidx.compose.foundation.layout.Spacer(modifier = Modifier.height(8.dp))
            ReviewOutcome.entries.forEach { outcome ->
                Row(
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    RadioButton(
                        selected = selectedOutcome == outcome,
                        onClick = { selectedOutcome = outcome }
                    )
                    Text(text = outcome.name.replace("_", " ").capitalize())
                }
                androidx.compose.foundation.layout.Spacer(modifier = Modifier.height(4.dp))
            }
            androidx.compose.foundation.layout.Spacer(modifier = Modifier.height(20.dp))
            Button(
                onClick = {
                    selectedOutcome?.let { outcome ->
                        onRecord(answer, outcome)
                    }
                },
                enabled = selectedOutcome != null,
                modifier = Modifier.fillMaxWidth()
            ) {
                Text(text = "Record attempt")
            }
        }
    }
}
