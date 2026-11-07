package com.ashura.tutor.data.profile

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.ashura.tutor.domain.LearnerLevel
import com.ashura.tutor.domain.TutorStyle
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * The learner profile is local-only UI preference state (spec §1.4): it must persist, reject unknown
 * enum names and unsupported languages, and expose changes through its StateFlow.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class LearnerProfileStoreTest {

    private lateinit var context: Context
    private lateinit var store: LearnerProfileStore

    @Before fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        context.getSharedPreferences("learner_profile", Context.MODE_PRIVATE).edit().clear().commit()
        store = LearnerProfileStore(context)
    }

    @Test fun defaultsAreDirectEnglishAndUnknownLevel() {
        val profile = store.profile.value
        assertEquals(LearnerLevel.UNKNOWN, profile.level)
        assertEquals(TutorStyle.DIRECT, profile.style)
        assertEquals("en", profile.language)
    }

    @Test fun updatePersistsAndEmits() {
        store.update(LearnerProfile(LearnerLevel.BACHELOR, TutorStyle.SOCRATIC, "ne"))

        assertEquals(LearnerLevel.BACHELOR, store.profile.value.level)
        assertEquals(TutorStyle.SOCRATIC, store.profile.value.style)
        assertEquals("ne", store.profile.value.language)

        val reopened = LearnerProfileStore(context)
        assertEquals(LearnerLevel.BACHELOR, reopened.profile.value.level)
        assertEquals(TutorStyle.SOCRATIC, reopened.profile.value.style)
        assertEquals("ne", reopened.profile.value.language)
    }

    @Test fun unknownStoredEnumFallsBackToDefaults() {
        context.getSharedPreferences("learner_profile", Context.MODE_PRIVATE).edit()
            .putString("level", "DOCTORATE").putString("style", "LECTURE").commit()

        val reopened = LearnerProfileStore(context)
        assertEquals(LearnerLevel.UNKNOWN, reopened.profile.value.level)
        assertEquals(TutorStyle.DIRECT, reopened.profile.value.style)
    }

    @Test fun unsupportedLanguageFallsBackToEnglish() {
        context.getSharedPreferences("learner_profile", Context.MODE_PRIVATE).edit()
            .putString("language", "fr").commit()

        assertEquals("en", LearnerProfileStore(context).profile.value.language)
    }

    @Test fun supportedLanguagesAreEnglishAndNepali() {
        assertEquals(setOf("en", "ne"), LearnerProfileStore.SUPPORTED_LANGUAGES)
    }
}
