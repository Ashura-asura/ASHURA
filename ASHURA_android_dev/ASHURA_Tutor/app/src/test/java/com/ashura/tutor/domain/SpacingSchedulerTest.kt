package com.ashura.tutor.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SpacingSchedulerTest {

    private val scheduler = SpacingScheduler()

    @Test fun incorrectResetsToShortInterval() {
        val schedule = scheduler.schedule(currentMastery = 0.8, currentIntervalDays = 10, outcome = ReviewOutcome.INCORRECT)
        assertEquals(1, schedule.nextIntervalDays)
        assertTrue(schedule.masteryEstimate < 0.8)
        assertTrue(schedule.nextReviewAt > 0)
    }

    @Test fun correctIndependentlyIncreasesInterval() {
        val schedule = scheduler.schedule(currentMastery = 0.5, currentIntervalDays = 2, outcome = ReviewOutcome.CORRECT_INDEPENDENTLY)
        assertEquals(4, schedule.nextIntervalDays)
        assertTrue(schedule.masteryEstimate > 0.5)
    }

    @Test fun intervalCapsAtThirtyDays() {
        var schedule = scheduler.schedule(currentMastery = 0.9, currentIntervalDays = 20, outcome = ReviewOutcome.CORRECT_INDEPENDENTLY)
        assertEquals(30, schedule.nextIntervalDays)
        // Repeated independent success stays capped.
        schedule = scheduler.schedule(currentMastery = schedule.masteryEstimate, currentIntervalDays = schedule.nextIntervalDays, outcome = ReviewOutcome.CORRECT_INDEPENDENTLY)
        assertEquals(30, schedule.nextIntervalDays)
    }

    @Test fun correctWithHelpGainsLessMasteryThanIndependent() {
        val withHelp = scheduler.schedule(currentMastery = 0.5, currentIntervalDays = 2, outcome = ReviewOutcome.CORRECT_WITH_HELP)
        val independent = scheduler.schedule(currentMastery = 0.5, currentIntervalDays = 2, outcome = ReviewOutcome.CORRECT_INDEPENDENTLY)
        assertTrue(independent.masteryEstimate > withHelp.masteryEstimate)
        assertTrue(independent.nextIntervalDays > withHelp.nextIntervalDays)
    }

    @Test fun masteryAndIntervalsStayWithinValidBounds() {
        val tooHigh = scheduler.schedule(1.5, 100, ReviewOutcome.CORRECT_WITH_HELP)
        assertEquals(1.0, tooHigh.masteryEstimate, 0.0)
        assertEquals(7, tooHigh.nextIntervalDays)

        val tooLow = scheduler.schedule(-0.5, -10, ReviewOutcome.INCORRECT)
        assertEquals(0.0, tooLow.masteryEstimate, 0.0)
        assertEquals(1, tooLow.nextIntervalDays)
    }
}
