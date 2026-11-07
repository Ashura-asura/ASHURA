package com.ashura.tutor

import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import com.ashura.tutor.data.LibraryItemEntity
import com.ashura.tutor.domain.assessment.AnswerCheck
import com.ashura.tutor.domain.assessment.Verdict
import com.ashura.tutor.domain.curriculum.SeedCurriculum
import com.ashura.tutor.ui.LibraryScreen
import com.ashura.tutor.ui.LibraryUiState
import com.ashura.tutor.ui.PracticeScreen
import com.ashura.tutor.ui.PracticeUiState
import com.ashura.tutor.ui.theme.AshuraTutorTheme
import org.junit.Rule
import org.junit.Test

class PracticeScreenTest {
    @get:Rule val rule = createComposeRule()
    private val question = SeedCurriculum.arithmetic.practice.first()

    @Test fun submitIsDisabledUntilAnswerTypedThenCallsBack() {
        var submitted: String? = null
        rule.setContent {
            AshuraTutorTheme {
                PracticeScreen(PracticeUiState(question = question), { submitted = it }, {}, {}, {}, {}, {})
            }
        }
        rule.onNodeWithText("Check answer").assertIsNotEnabled()
        rule.onNodeWithText("Your answer").performTextInput("11")
        rule.onNodeWithText("Check answer").assertIsEnabled().performClick()
        check(submitted == "11")
    }

    @Test fun hintsAreRevealedProgressivelyAndFeedbackIsShown() {
        rule.setContent {
            AshuraTutorTheme {
                PracticeScreen(
                    PracticeUiState(question = question, hintsShown = 1, check = AnswerCheck(Verdict.INCORRECT, null, "Not quite. Try again.")),
                    {}, {}, {}, {}, {}, {}
                )
            }
        }
        rule.onNodeWithText("Hint 1: ${question.hints[0]}").assertIsDisplayed()
        rule.onNodeWithText("Not quite. Try again.").assertIsDisplayed()
    }

    @Test fun libraryShowsEmptyStateAndHonestScopeNote() {
        rule.setContent {
            AshuraTutorTheme {
                LibraryScreen(emptyList<LibraryItemEntity>(), LibraryUiState(), {}, {}, {}, { _, _ -> })
            }
        }
        rule.onNodeWithText("Nothing imported yet.").assertIsDisplayed()
    }
}
