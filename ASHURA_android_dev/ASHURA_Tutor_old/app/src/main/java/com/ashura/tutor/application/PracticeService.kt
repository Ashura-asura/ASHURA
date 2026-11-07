package com.ashura.tutor.application

import com.ashura.tutor.data.AttemptEntity
import com.ashura.tutor.data.LearningStateEntity
import com.ashura.tutor.data.TutorRepository
import com.ashura.tutor.domain.PracticeQuestion
import com.ashura.tutor.domain.ReviewOutcome
import com.ashura.tutor.domain.ReviewSchedule
import com.ashura.tutor.domain.SpacingScheduler
import com.ashura.tutor.domain.assessment.AnswerCheck
import com.ashura.tutor.domain.assessment.AnswerChecker
import com.ashura.tutor.domain.assessment.Verdict
import com.ashura.tutor.domain.curriculum.CurriculumPack
import java.util.UUID

data class PracticeOutcome(val check: AnswerCheck, val schedule: ReviewSchedule?)

/**
 * Application-layer use case: check an answer deterministically, update mastery/spacing from stored
 * state, and persist everything atomically (spec §12.3, §7.5). Independent success and success after
 * hints are recorded separately.
 */
class PracticeService(
    private val repository: TutorRepository,
    private val checker: AnswerChecker,
    private val scheduler: SpacingScheduler,
    private val pack: CurriculumPack,
    private val clock: () -> Long = System::currentTimeMillis
) {
    suspend fun submit(question: PracticeQuestion, answer: String, hintsUsed: Int, solutionViewed: Boolean, priorIncorrect: Int = 0): PracticeOutcome {
        require(!question.selfAssessed) { "Use submitSelfAssessed for self-assessed questions." }
        val topic = pack.topic(question.conceptId)
        val check = checker.check(question, answer) { tag -> topic?.misconceptions?.firstOrNull { it.tag == tag } }
        if (check.verdict == Verdict.UNREADABLE) return PracticeOutcome(check, null) // not an attempt; nothing persisted
        val outcome = when {
            check.verdict == Verdict.INCORRECT -> ReviewOutcome.INCORRECT
            // A correct answer after a failed try on the same question is not independent mastery.
            hintsUsed > 0 || solutionViewed || priorIncorrect > 0 -> ReviewOutcome.CORRECT_WITH_HELP
            else -> ReviewOutcome.CORRECT_INDEPENDENTLY
        }
        // Only the first wrong answer to a question lowers mastery; further wrong tries are logged but not penalised again.
        val applyMastery = !(outcome == ReviewOutcome.INCORRECT && priorIncorrect > 0)
        val schedule = persist(question, answer.trim().take(200), check.verdict.name, hintsUsed, check.misconceptionTag, outcome, applyMastery)
        return PracticeOutcome(check, schedule)
    }

    suspend fun submitSelfAssessed(question: PracticeQuestion, outcome: ReviewOutcome): ReviewSchedule =
        persist(question, "", "SELF_${outcome.name}", 0, null, outcome, true)

    private suspend fun persist(
        question: PracticeQuestion, answer: String, verdict: String, hintsUsed: Int,
        tag: String?, outcome: ReviewOutcome, applyMastery: Boolean
    ): ReviewSchedule {
        val now = clock()
        val previous = repository.getLearningState(question.conceptId)
        val schedule = if (applyMastery || previous == null) scheduler.schedule(previous?.masteryEstimate ?: 0.0, previous?.intervalDays ?: 1, outcome, now)
        else ReviewSchedule(previous.intervalDays, previous.masteryEstimate, previous.nextReviewAt)
        val attempts = repository.attemptCount(question.conceptId) + 1
        // Confidence reflects how much evidence exists, not model certainty: saturates after 5 attempts.
        val confidence = (attempts / 5.0).coerceAtMost(1.0)
        val resolved = if (outcome == ReviewOutcome.CORRECT_INDEPENDENTLY) question.misconceptionsByAnswer.values.distinct() else emptyList()
        repository.commitAttempt(
            AttemptEntity(UUID.randomUUID().toString(), question.conceptId, question.id, answer, verdict, hintsUsed, tag, now),
            LearningStateEntity(question.conceptId, schedule.masteryEstimate, confidence, schedule.nextReviewAt, schedule.nextIntervalDays),
            tag, resolved
        )
        return schedule
    }
}
