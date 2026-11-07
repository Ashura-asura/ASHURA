package com.ashura.tutor.data.profile

import android.content.Context
import androidx.core.content.edit
import com.ashura.tutor.domain.LearnerLevel
import com.ashura.tutor.domain.TutorStyle
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Local learner preferences (spec §1.4, §3.6): level, teaching style and answer language.
 * Stored in plain SharedPreferences because they are not sensitive; no account or sync exists.
 */
data class LearnerProfile(
    val level: LearnerLevel = LearnerLevel.UNKNOWN,
    val style: TutorStyle = TutorStyle.DIRECT,
    val language: String = "en"
)

class LearnerProfileStore(context: Context) {
    private val prefs = context.getSharedPreferences("learner_profile", Context.MODE_PRIVATE)
    private val _profile = MutableStateFlow(read())
    val profile: StateFlow<LearnerProfile> = _profile.asStateFlow()

    fun update(profile: LearnerProfile) {
        prefs.edit {
            putString(KEY_LEVEL, profile.level.name)
            putString(KEY_STYLE, profile.style.name)
            putString(KEY_LANGUAGE, profile.language)
        }
        _profile.value = profile
    }

    private fun read(): LearnerProfile {
        val level = prefs.getString(KEY_LEVEL, null)
            ?.let { name -> LearnerLevel.entries.firstOrNull { it.name == name } }
            ?: LearnerLevel.UNKNOWN
        val style = prefs.getString(KEY_STYLE, null)
            ?.let { name -> TutorStyle.entries.firstOrNull { it.name == name } }
            ?: TutorStyle.DIRECT
        val language = prefs.getString(KEY_LANGUAGE, null)?.takeIf { it in SUPPORTED_LANGUAGES } ?: "en"
        return LearnerProfile(level, style, language)
    }

    companion object {
        private const val KEY_LEVEL = "level"
        private const val KEY_STYLE = "style"
        private const val KEY_LANGUAGE = "language"
        val SUPPORTED_LANGUAGES = setOf("en", "ne")
    }
}
