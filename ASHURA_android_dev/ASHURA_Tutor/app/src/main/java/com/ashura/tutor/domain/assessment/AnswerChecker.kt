package com.ashura.tutor.domain.assessment

import com.ashura.tutor.domain.PracticeQuestion
import com.ashura.tutor.domain.curriculum.Misconception
import com.ashura.tutor.domain.math.DigitNormalizer
import java.math.BigDecimal
import java.math.BigInteger

enum class Verdict { CORRECT, INCORRECT, UNREADABLE }

data class AnswerCheck(
    val verdict: Verdict,
    val misconceptionTag: String? = null,
    val feedback: String
)

/** Exact rational number; lets "0.5", "1/2" and "2/4" compare exactly (spec §12.1, deterministic checks first). */
data class Rational(val num: BigInteger, val den: BigInteger) {
    init { require(den.signum() > 0) }
    fun reduced(): Rational {
        if (num.signum() == 0) return Rational(BigInteger.ZERO, BigInteger.ONE)
        val g = num.gcd(den)
        return Rational(num / g, den / g)
    }
    fun toDouble(): Double = BigDecimal(num).divide(BigDecimal(den), java.math.MathContext.DECIMAL64).toDouble()

    companion object {
        /** Parses integers, decimals and "a/b" (no spaces needed). Returns null if not a plain number. */
        fun parse(text: String): Rational? {
            val t = text.trim()
            val slash = t.indexOf('/')
            return try {
                if (slash >= 0) {
                    val n = decimal(t.substring(0, slash)) ?: return null
                    val d = decimal(t.substring(slash + 1)) ?: return null
                    if (d.num.signum() == 0) return null
                    val numer = n.num * d.den
                    val denom = n.den * d.num
                    if (denom.signum() < 0) Rational(-numer, -denom) else Rational(numer, denom)
                } else decimal(t)
            } catch (_: NumberFormatException) { null }
        }

        private val plain = Regex("^[+-]?(\\d+(\\.\\d+)?|\\.\\d+)$")
        private fun decimal(t: String): Rational? {
            if (!plain.matches(t) || t.length > 40) return null
            val bd = BigDecimal(t)
            val unscaled = bd.unscaledValue()
            return if (bd.scale() >= 0) Rational(unscaled, BigInteger.TEN.pow(bd.scale()))
            else Rational(unscaled * BigInteger.TEN.pow(-bd.scale()), BigInteger.ONE)
        }
    }
}

/**
 * Deterministic answer checking for machine-checkable practice (spec §12.3).
 * Never calls a model. Detects known misconceptions from specific wrong answers.
 */
class AnswerChecker {

    fun check(
        question: PracticeQuestion,
        rawAnswer: String,
        misconception: (String) -> Misconception? = { null }
    ): AnswerCheck {
        require(!question.selfAssessed) { "Self-assessed questions cannot be machine-checked." }
        val answer = normalize(rawAnswer)
        if (answer.isEmpty()) return AnswerCheck(Verdict.UNREADABLE, null, "Type an answer first.")

        val learner = Rational.parse(answer)
        val expectedForms = (listOf(question.expectedAnswer) + question.acceptedAnswers).map { normalize(it) }

        if (matchesAny(question, answer, learner, expectedForms)) {
            return AnswerCheck(Verdict.CORRECT, null, "Correct." + (question.explanation?.let { " $it" } ?: ""))
        }
        if (learner == null && expectedForms.none { Rational.parse(it) == null }) {
            return AnswerCheck(Verdict.UNREADABLE, null, "I could not read that as a number. Enter a number or a fraction like 3/4.")
        }
        // Valid value but not in lowest terms?
        if (question.requireLowestTerms && learner != null &&
            expectedForms.any { e -> Rational.parse(e)?.reduced() == learner.reduced() }
        ) {
            return AnswerCheck(Verdict.INCORRECT, null, "The value is right, but simplify it to lowest terms.")
        }

        val tag = question.misconceptionsByAnswer.entries.firstOrNull { (wrong, _) ->
            val w = normalize(wrong)
            val wr = Rational.parse(w)
            if (learner != null && wr != null) learner.reduced() == wr.reduced() else w == answer
        }?.value
        val detail = tag?.let(misconception)
        val feedback = if (detail != null) "Not quite. ${detail.description} ${detail.correction}" else "Not quite. Try again, or use a hint."
        return AnswerCheck(Verdict.INCORRECT, tag, feedback)
    }

    private fun matchesAny(q: PracticeQuestion, answer: String, learner: Rational?, forms: List<String>): Boolean {
        for (form in forms) {
            val expected = Rational.parse(form)
            if (learner != null && expected != null) {
                if (q.tolerance > 0.0) {
                    if (kotlin.math.abs(learner.toDouble() - expected.toDouble()) <= q.tolerance) return true
                } else if (learner.reduced() == expected.reduced()) {
                    if (!q.requireLowestTerms || learner == learner.reduced()) return true
                }
            } else if (answer == form) return true
        }
        return false
    }

    internal fun normalize(raw: String): String {
        var t = DigitNormalizer.toAscii(raw).trim().lowercase().replace('−', '-').replace(" ", "")
        t = t.replace(Regex("^(?:[a-z]=|answer:|ans:)"), "").trimEnd('.')
        if (Regex("^[+-]?\\d{1,3}(,\\d{3})+(\\.\\d+)?$").matches(t)) t = t.replace(",", "")
        return t
    }
}
