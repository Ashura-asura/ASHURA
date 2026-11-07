package com.ashura.tutor.domain

import com.ashura.tutor.domain.assessment.AnswerChecker
import com.ashura.tutor.domain.assessment.MistakeExplainer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class MistakeExplainerTest {
    private val checker = AnswerChecker()
    private fun q(expected: String, explanation: String? = "Add the numerators.", hints: List<String> = listOf("h"), map: Map<String, String> = emptyMap()) =
        PracticeQuestion(id = "q", conceptId = "c", prompt = "p", expectedAnswer = expected, explanation = explanation, hints = hints, misconceptionsByAnswer = map)

    private fun explain(question: PracticeQuestion, answer: String) =
        MistakeExplainer.explain(question, answer, checker.check(question, answer))

    @Test fun correctAnswerNeedsNoExplanation() = assertNull(explain(q("5"), "5"))

    @Test fun unreadableAnswerNeedsNoExplanation() = assertNull(explain(q("5"), "abc"))

    @Test fun reportsComparisonAndMethod() {
        val e = explain(q("5"), "7")!!
        assertEquals("You answered 7; the correct answer is 5.", e.comparison)
        assertEquals("Add the numerators.", e.method)
    }

    @Test fun largerAndSmallerAreStated() {
        assertTrue(explain(q("5"), "7")!!.why!!.contains("larger"))
        assertTrue(explain(q("5"), "3")!!.why!!.contains("smaller"))
    }

    @Test fun detectsSignSlip() = assertTrue(explain(q("5"), "-5")!!.why!!.contains("sign"))

    @Test fun detectsDecimalSlip() {
        assertTrue(explain(q("5"), "50")!!.why!!.contains("factor of 10"))
        assertTrue(explain(q("5"), "0.5")!!.why!!.contains("factor of 10"))
    }

    @Test fun knownMisconceptionUsesItsFeedback() {
        val question = q("1/2", map = mapOf("2/4x" to "tag"))
        val check = com.ashura.tutor.domain.assessment.AnswerCheck(
            com.ashura.tutor.domain.assessment.Verdict.INCORRECT, "tag", "Not quite. You added the denominators. Keep the denominator."
        )
        val e = MistakeExplainer.explain(question, "2/4x", check)!!
        assertEquals("You added the denominators. Keep the denominator.", e.why)
    }

    @Test fun missingExplanationGivesNullMethod() = assertNull(explain(q("5", explanation = null), "7")!!.method)

    @Test fun nextStepMentionsHintOnlyWhenOneExists() {
        assertTrue(explain(q("5"), "7")!!.next.contains("hint"))
        assertTrue(!explain(q("5", hints = emptyList()), "7")!!.next.contains("hint"))
        assertNotNull(explain(q("5"), "7"))
    }
}
