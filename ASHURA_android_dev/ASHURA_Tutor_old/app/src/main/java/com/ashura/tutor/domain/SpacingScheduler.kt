package com.ashura.tutor.domain

/**
 * Spaced-repetition scheduler (spec §7.5, §9.4).
 * A simple, testable schedule first; record independent success separately
 * from success after hints.
 */
enum class ReviewOutcome { INCORRECT, CORRECT_WITH_HELP, CORRECT_INDEPENDENTLY }

data class ReviewSchedule(
    val nextIntervalDays: Int,
    val masteryEstimate: Double,
    val nextReviewAt: Long
)

class SpacingScheduler {

    fun schedule(
        currentMastery: Double,
        currentIntervalDays: Int,
        outcome: ReviewOutcome,
        now: Long = System.currentTimeMillis()
    ): ReviewSchedule {
        val mastery = currentMastery.coerceIn(0.0, 1.0)
        val interval = currentIntervalDays.coerceIn(1, 30)
        val nextMastery = when (outcome) {
            ReviewOutcome.INCORRECT -> (mastery - 0.2).coerceAtLeast(0.0)
            ReviewOutcome.CORRECT_WITH_HELP -> (mastery + 0.1).coerceAtMost(1.0)
            ReviewOutcome.CORRECT_INDEPENDENTLY -> (mastery + 0.2).coerceAtMost(1.0)
        }
        val nextInterval = when (outcome) {
            ReviewOutcome.INCORRECT -> 1
            ReviewOutcome.CORRECT_WITH_HELP -> (interval + 1).coerceAtMost(7)
            ReviewOutcome.CORRECT_INDEPENDENTLY -> (interval * 2).coerceAtMost(30)
        }
        return ReviewSchedule(
            nextIntervalDays = nextInterval,
            masteryEstimate = nextMastery,
            nextReviewAt = now + nextInterval * 86_400_000L
        )
    }

}
