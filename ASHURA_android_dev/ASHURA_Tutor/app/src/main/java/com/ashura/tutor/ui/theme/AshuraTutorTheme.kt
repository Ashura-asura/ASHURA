package com.ashura.tutor.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// Neutral conversational palette (white canvas, quiet grey surfaces, one indigo accent).
// Text/background pairs are checked against WCAG AA (>= 4.5:1).
private val LightColors = lightColorScheme(
    primary = Color(0xFF344A9A),
    onPrimary = Color.White,
    primaryContainer = Color(0xFFE5E9FF),
    onPrimaryContainer = Color(0xFF15245C),
    secondary = Color(0xFF53627D),
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFE8ECF6),
    onSecondaryContainer = Color(0xFF1B2436),
    background = Color(0xFFFFFFFF),
    onBackground = Color(0xFF16181D),
    surface = Color(0xFFFFFFFF),
    onSurface = Color(0xFF16181D),
    surfaceVariant = Color(0xFFF2F3F7),
    onSurfaceVariant = Color(0xFF5B6270),
    outline = Color(0xFF8A909C),
    outlineVariant = Color(0xFFE4E6EC),
    error = Color(0xFFB3261E),
    onError = Color.White
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFFB4C0FF),
    onPrimary = Color(0xFF1B2A6B),
    primaryContainer = Color(0xFF2A3566),
    onPrimaryContainer = Color(0xFFDDE1FF),
    secondary = Color(0xFFBAC6E4),
    onSecondary = Color(0xFF212833),
    secondaryContainer = Color(0xFF2A3142),
    onSecondaryContainer = Color(0xFFDDE3F2),
    background = Color(0xFF0F1013),
    onBackground = Color(0xFFE7E8EC),
    surface = Color(0xFF0F1013),
    onSurface = Color(0xFFE7E8EC),
    surfaceVariant = Color(0xFF23252B),
    onSurfaceVariant = Color(0xFFB9BDC7),
    outline = Color(0xFF8B909C),
    outlineVariant = Color(0xFF30333A),
    error = Color(0xFFFFB4AB),
    onError = Color(0xFF690005)
)

@Composable
fun AshuraTutorTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (darkTheme) DarkColors else LightColors, content = content)
}
