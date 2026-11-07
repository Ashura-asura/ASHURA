package com.ashura.tutor.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LessonPlannerTest {

    private val planner = LessonPlanner()

    @Test fun planReturnsInspectableStructure() {
        val lesson = planner.plan(subject = "Mathematics", topic = "Arithmetic", level = LearnerLevel.SCHOOL)
        assertEquals("Mathematics", lesson.subject)
        assertEquals("Arithmetic", lesson.topic)
        assertEquals(LearnerLevel.SCHOOL, lesson.level)
        assertTrue(lesson.objectives.isNotEmpty())
        assertTrue(lesson.explanationOutline.isNotEmpty())
        assertNotNull(lesson.workedExample)
        assertTrue(lesson.practiceQuestions.isNotEmpty())
        // Every practice question is tied to the stable concept id for mastery tracking.
        assertEquals("math.arithmetic", lesson.topicId)
        lesson.practiceQuestions.forEach { assertEquals("math.arithmetic", it.conceptId) }
        assertTrue(lesson.misconceptions.isNotEmpty())
        assertTrue(lesson.sourceRefs.isNotEmpty())
        assertFalse(lesson.isGenericScaffold)
    }

    @Test fun unknownTopicIsALabelledScaffoldWithSelfAssessedPractice() {
        val lesson = planner.plan("Geography", "Rivers", LearnerLevel.SCHOOL)
        assertTrue(lesson.isGenericScaffold)
        assertEquals(null, lesson.workedExample)
        assertTrue(lesson.practiceQuestions.all { it.selfAssessed })
    }
}
