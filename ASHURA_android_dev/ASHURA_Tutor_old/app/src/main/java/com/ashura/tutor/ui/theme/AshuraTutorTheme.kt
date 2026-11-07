package com.ashura.tutor.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val AshuraColors = lightColorScheme(
    primary = Color(0xFF344A9A), onPrimary = Color.White,
    secondary = Color(0xFF53627D), background = Color(0xFFF7F8FC),
    surface = Color.White, error = Color(0xFFB3261E)
)

@Composable
fun AshuraTutorTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = AshuraColors, content = content)
}
