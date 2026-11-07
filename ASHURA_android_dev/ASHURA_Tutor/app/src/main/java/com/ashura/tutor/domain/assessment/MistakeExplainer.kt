package com.ashura.tutor.domain.assessment

import com.ashura.tutor.domain.PracticeQuestion
import java.math.BigInteger

/**
 * Deterministic "Explain my mistake" for machine-checked practice (spec §3.4). It only states what can be
 * proven from the learner's answer and the question data; it never guesses at the learner's working.
 */
data class MistakeExplanation(
    /** What was compared, e.g. "You answered 3/4; the correct value is 1/2." */
    val comparison: String,
    /** Why it is wrong, from a known misconception or from a provable numeric pattern; null if unknown. */
    val why: String?,
    /** The corrected method, taken from the question's own explanation; null if the question has none. */
    val method: String?,
    /** What to do next. */
    val next: String
)

object MistakeExplainer {
    fun explain(
        question: PracticeQuestion,
        learnerAnswer: String,
        check: AnswerCheck,
        checker: AnswerChecker = AnswerChecker()
    ): MistakeExplanation? {
        if (check.verdict != Verdict.INCORRECT) return null
        val learnerText = learnerAnswer.trim()
        val comparison = "You answered $learnerText; the correct answer is ${question.expectedAnswer}."

        val learner = Rational.parse(checker.normalize(learnerAnswer))?.reduced()
        val expected = Rational.parse(checker.normalize(question.expectedAnswer))?.reduced()

        val why = when {
            // Known misconception: the checker already put its description and correction in the feedback.
            check.misconceptionTag != null -> check.feedback.removePrefix("Not quite.").trim().ifBlank { null }
            learner != null && expected != null -> numericPattern(learner, expected)
            else -> null
        }
        val method = question.explanation?.takeIf { it.isNotBlank() }
        val next = if (question.hints.isNotEmpty()) "Use a hint, then try a similar question."
        else "Try again, then try a similar question."
        return MistakeExplanation(comparison, why, method, next)
    }

    private fun numericPattern(learner: Rational, expected: Rational): String? {
        // Same size, opposite sign.
        if (learner.num.signum() != 0 && learner.num == expected.num.negate() && learner.den == expected.den) {
            return "Your answer has the right size but the wrong sign. Re-check how the negatives combine."
        }
        // Out by a power of ten (decimal point slip).
        if (learner.num.signum() != 0 && expected.num.signum() != 0) {
            val ratioNum = learner.num * expected.den
            val ratioDen = learner.den * expected.num
            for (p in 1..4) {
                val ten = BigInteger.TEN.pow(p)
                if (ratioNum.abs() == ratioDen.abs() * ten || ratioNum.abs() * ten == ratioDen.abs()) {
                    return "Your answer is out by a factor of ${ten}. Check where the decimal point goes."
                }
            }
        }
        val cmp = (learner.num * expected.den).compareTo(expected.num * learner.den)
        return when {
            cmp > 0 -> "Your answer is larger than the correct value."
            cmp < 0 -> "Your answer is smaller than the correct value."
            else -> null
        }
    }
}
