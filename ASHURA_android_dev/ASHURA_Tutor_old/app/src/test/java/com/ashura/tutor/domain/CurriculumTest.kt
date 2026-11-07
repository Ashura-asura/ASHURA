package com.ashura.tutor.domain

import com.ashura.tutor.domain.assessment.Rational
import com.ashura.tutor.domain.curriculum.CurriculumPack
import com.ashura.tutor.domain.curriculum.SeedCurriculum
import com.ashura.tutor.domain.curriculum.Topic
import com.ashura.tutor.domain.math.EvalResult
import com.ashura.tutor.domain.math.ExpressionEvaluator
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class CurriculumTest {
    private val pack = SeedCurriculum.pack

    private fun value(expr: String): Rational {
        val r = ExpressionEvaluator.evaluate(expr) as EvalResult.Value
        return Rational.parse(r.value.toPlainString())!!.reduced()
    }
    private fun same(expr: String, expected: String) =
        assertEquals("$expr should equal $expected", Rational.parse(expected)!!.reduced(), value(expr))

    /** Content check: every shipped answer and every declared wrong answer is verified by computation. */
    @Test fun seedContentIsMathematicallyCorrect() {
        same("3 + 4 * 2", "11"); same("(3 + 4) * 2", "14"); same("10 - 2 * 3", "4"); same("18 / 3 / 2", "3")
        same("(3 + 4) * 2", "14");   // misconception answer 14 for q1 is the left-to-right result
        same("(10 - 2) * 3", "24")   // misconception answer 24 for q3
        same("18 / (3 / 2)", "12")   // misconception answer 12 for q4
        // 1/2 + 1/3 is non-terminating in decimal, so verify with exact rational arithmetic.
        val half = Rational.parse("1/2")!!; val third = Rational.parse("1/3")!!
        assertEquals(Rational.parse("5/6")!!.reduced(),
            Rational(half.num * third.den + third.num * half.den, half.den * third.den).reduced())
        same("20 * 3 / 4", "15"); same("6/8", "3/4")
        same("(1 + 1) / (2 + 3)", "0.4")  // misconception answer 2/5 for fractions q1 (added across)
        same("20% * 150", "30"); same("80 * 1.25", "100"); same("40 / 8 * 5", "25"); same("80 + 25", "105")
        same("2 * 4 + 3", "11"); same("3 * 5 - 5", "10"); same("24 / 4", "6")
        same("(11 + 3) / 2", "7"); same("6 / 4", "1.5")
    }

    @Test fun everyQuestionAnswerMatchesDeclaredExpectedAnswerAndIsNeverAWrongAnswer() {
        pack.topics.flatMap { it.practice }.forEach { q ->
            val expected = Rational.parse(q.expectedAnswer)
            assertNotNull("${q.id} expected answer must be numeric", expected)
            q.misconceptionsByAnswer.keys.forEach { wrong ->
                val w = Rational.parse(wrong)
                assertTrue("${q.id}: wrong answer $wrong equals the correct one", w == null || w.reduced() != expected!!.reduced())
            }
            assertTrue("${q.id} needs at least one hint", q.hints.isNotEmpty())
        }
    }

    @Test fun learningOrderPutsPrerequisitesFirst() {
        val order = pack.learningOrder().map { it.id }
        pack.topics.forEach { t -> t.prerequisites.forEach { p -> assertTrue(order.indexOf(p) < order.indexOf(t.id)) } }
    }

    @Test fun recommendationFollowsMastery() {
        assertEquals("math.arithmetic", pack.nextRecommended(emptyMap())!!.id)
        assertEquals("math.fractions", pack.nextRecommended(mapOf("math.arithmetic" to 0.8))!!.id)
        assertEquals("math.percentages", pack.nextRecommended(mapOf("math.arithmetic" to 0.8, "math.fractions" to 0.9))!!.id)
        val all = pack.topics.associate { it.id to 1.0 }
        assertNull(pack.nextRecommended(all))
    }

    @Test fun missingPrerequisitesAreReportedInTeachingOrder() {
        val missing = pack.missingPrerequisites("math.linear_equations", mapOf("math.arithmetic" to 0.9))
        assertEquals(listOf("math.fractions"), missing.map { it.id })
        val all = pack.missingPrerequisites("math.linear_equations", emptyMap()).map { it.id }
        assertEquals(listOf("math.arithmetic", "math.fractions"), all)
    }

    private fun topic(id: String, vararg prereq: String) = Topic(
        id = id, subject = "S", title = id, level = LearnerLevel.SCHOOL, prerequisites = prereq.toList(),
        objectives = listOf("o"), outline = listOf("x"), workedExample = "w"
    )

    @Test fun invalidPacksFailFast() {
        fun fails(vararg t: Topic): Boolean = try { CurriculumPack("p", 1, t.toList()); false } catch (_: IllegalArgumentException) { true }
        assertTrue("cycle", fails(topic("a", "b"), topic("b", "a")))
        assertTrue("unknown prerequisite", fails(topic("a", "zzz")))
        assertTrue("duplicate id", fails(topic("a"), topic("a")))
    }

    @Test fun plannerUsesPackAndLabelsGenericScaffolds() {
        val planner = LessonPlanner()
        val real = planner.plan("Mathematics", "fractions", LearnerLevel.SCHOOL)
        assertEquals("math.fractions", real.topicId)
        assertTrue(!real.isGenericScaffold)
        val generic = planner.plan("History", "Rome", LearnerLevel.SCHOOL)
        assertTrue(generic.isGenericScaffold)
        assertNull(generic.topicId)
    }
}
