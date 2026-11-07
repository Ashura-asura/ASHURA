package com.ashura.tutor.domain

import com.ashura.tutor.domain.assessment.AnswerChecker
import com.ashura.tutor.domain.assessment.Rational
import com.ashura.tutor.domain.assessment.Verdict
import com.ashura.tutor.domain.curriculum.SeedCurriculum
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AnswerCheckerTest {
    private val checker = AnswerChecker()
    private val pack = SeedCurriculum.pack
    private fun q(id: String) = pack.topics.flatMap { it.practice }.first { it.id == id }
    private fun check(id: String, a: String) = checker.check(q(id), a) { tag -> pack.topics.flatMap { it.misconceptions }.firstOrNull { it.tag == tag } }

    @Test fun rationalParsingIsExact() {
        assertEquals(Rational.parse("0.5")!!.reduced(), Rational.parse("1/2")!!.reduced())
        assertEquals(Rational.parse("2/4")!!.reduced(), Rational.parse("1/2")!!.reduced())
        assertNull(Rational.parse("1/0"))
        assertNull(Rational.parse("abc"))
        assertNull(Rational.parse("3+4"))
    }

    @Test fun correctAnswersInEquivalentForms() {
        assertEquals(Verdict.CORRECT, check("math.arithmetic:q1", "11").verdict)
        assertEquals(Verdict.CORRECT, check("math.arithmetic:q1", " x = 11. ").verdict)
        assertEquals(Verdict.CORRECT, check("math.fractions:q1", "10/12").verdict)
        assertEquals(Verdict.CORRECT, check("math.linear_equations:q3", "24.0").verdict)
    }

    @Test fun knownWrongAnswerYieldsMisconception() {
        val r = check("math.arithmetic:q1", "14")
        assertEquals(Verdict.INCORRECT, r.verdict)
        assertEquals("arith.left_to_right", r.misconceptionTag)
        assertTrue(r.feedback.contains("priority"))
        assertEquals("frac.add_across", check("math.fractions:q1", "2/5").misconceptionTag)
        assertEquals("lin.wrong_inverse", check("math.linear_equations:q1", "7").misconceptionTag)
    }

    @Test fun unknownWrongAnswerHasNoMisconception() {
        val r = check("math.arithmetic:q1", "99")
        assertEquals(Verdict.INCORRECT, r.verdict)
        assertNull(r.misconceptionTag)
    }

    @Test fun lowestTermsIsEnforced() {
        assertEquals(Verdict.CORRECT, check("math.fractions:q3", "3/4").verdict)
        val r = check("math.fractions:q3", "6/8")
        assertEquals(Verdict.INCORRECT, r.verdict)
        assertTrue(r.feedback.contains("lowest terms"))
    }

    @Test fun unreadableAndBlankInput() {
        assertEquals(Verdict.UNREADABLE, check("math.arithmetic:q1", "").verdict)
        assertEquals(Verdict.UNREADABLE, check("math.arithmetic:q1", "eleven").verdict)
    }

    @Test fun selfAssessedQuestionsCannotBeMachineChecked() {
        val generic = LessonPlanner().plan("History", "Rome", LearnerLevel.SCHOOL).practiceQuestions.first()
        try { checker.check(generic, "x"); throw AssertionError("expected IllegalArgumentException") }
        catch (_: IllegalArgumentException) { }
    }
}
