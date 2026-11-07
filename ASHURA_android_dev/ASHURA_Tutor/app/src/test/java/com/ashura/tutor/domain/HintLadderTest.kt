package com.ashura.tutor.domain

import com.ashura.tutor.domain.assessment.HintLadder
import com.ashura.tutor.domain.assessment.LadderStep
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class HintLadderTest {
    @Test fun freshQuestionNeedsNothing() =
        assertEquals(LadderStep.NONE, HintLadder.nextStep(3, 0, 0, false))

    @Test fun firstWrongAnswerSuggestsHint() =
        assertEquals(LadderStep.SUGGEST_HINT, HintLadder.nextStep(3, 0, 1, false))

    @Test fun hintAlreadyTakenForThatMistakeStaysQuiet() =
        assertEquals(LadderStep.NONE, HintLadder.nextStep(3, 1, 1, false))

    @Test fun stuckWithAllHintsUsedOffersSolution() =
        assertEquals(LadderStep.OFFER_SOLUTION, HintLadder.nextStep(2, 2, 2, false))

    @Test fun stuckWithNoHintsAtAllOffersSolution() =
        assertEquals(LadderStep.OFFER_SOLUTION, HintLadder.nextStep(0, 0, 2, false))

    @Test fun askingForAnswerAlwaysReachesSolution() =
        assertEquals(LadderStep.OFFER_SOLUTION, HintLadder.nextStep(3, 0, 0, false, askedForAnswer = true))

    @Test fun solutionShownEndsTheLadder() =
        assertEquals(LadderStep.NONE, HintLadder.nextStep(3, 3, 5, true))

    @Test fun detectsDirectAnswerRequests() {
        assertTrue(HintLadder.asksForDirectAnswer("Please just tell me the answer"))
        assertFalse(HintLadder.asksForDirectAnswer("How do I factor this?"))
    }

    @Test fun detectsFullDerivationRequests() {
        assertTrue(HintLadder.asksForDirectAnswer("Show the full derivation of the quadratic formula"))
        assertTrue(HintLadder.asksForDirectAnswer("Please give me the complete solution"))
        assertTrue(HintLadder.asksForDirectAnswer("show all steps"))
        assertFalse(HintLadder.asksForDirectAnswer("What is the derivative of x squared?"))
    }
}
