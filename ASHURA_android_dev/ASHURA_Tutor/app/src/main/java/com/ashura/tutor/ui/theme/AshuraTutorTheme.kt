package com.ashura.tutor.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// Contrast checked against WCAG AA (>= 4.5:1) for primary/error text on their backgrounds.
private val LightColors = lightColorScheme(
    primary = Color(0xFF344A9A), onPrimary = Color.White,
    secondary = Color(0xFF53627D), background = Color(0xFFF7F8FC),
    surface = Color.White, error = Color(0xFFB3261E)
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFFB4C0FF), onPrimary = Color(0xFF1B2A6B),
    secondary = Color(0xFFBAC6E4), background = Color(0xFF111318),
    surface = Color(0xFF111318), error = Color(0xFFFFB4AB), onError = Color(0xFF690005)
)

@Composable
fun AshuraTutorTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (darkTheme) DarkColors else LightColors, content = content)
}
