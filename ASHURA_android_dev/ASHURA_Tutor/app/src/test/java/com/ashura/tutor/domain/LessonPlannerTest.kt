package com.ashura.tutor.domain

import org.junit.Assert.assertEquals
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
        // Every practice question is tied to a concept for mastery tracking.
        lesson.practiceQuestions.forEach {
            assertNotNull(it.conceptId)
            assertEquals("Arithmetic", it.conceptId)
        }
        assertTrue(lesson.misconceptions.isEmpty())
        assertTrue(lesson.sourceRefs.isEmpty())
    }
}
