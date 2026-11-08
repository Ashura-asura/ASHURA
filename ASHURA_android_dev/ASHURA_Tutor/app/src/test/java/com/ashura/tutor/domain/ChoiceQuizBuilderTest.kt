package com.ashura.tutor.domain

import com.ashura.tutor.domain.assessment.ChoiceQuizBuilder
import com.ashura.tutor.domain.assessment.QuizSource
import com.ashura.tutor.domain.library.TextChunker
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ChoiceQuizBuilderTest {

    private fun source(title: String, text: String) =
        QuizSource(title, TextChunker.chunk(TextChunker.normalize(text)).chunks)

    private val physics = source(
        "Physics basics",
        """
            Gravity is a force that pulls two masses toward each other.
            Friction is a force that opposes motion between two touching surfaces.
            Energy is the capacity of a system to do work or transfer heat.
            Momentum is the product of an object's mass and its velocity.
            Acceleration is the rate at which speed changes with time.
            Power is the rate at which work is done or energy is transferred.
        """.trimIndent()
    )

    @Test
    fun buildsFourDistinctOptionsAndNoFillInTheBlank() {
        val questions = ChoiceQuizBuilder.build(listOf(physics), 8)
        assertEquals(8, questions.size)
        for (question in questions) {
            assertEquals(4, question.options.size)
            assertEquals(4, question.options.distinct().size)
            assertTrue(question.correctIndex in 0..3)
            assertTrue(question.options[question.correctIndex].isNotBlank())
            assertFalse(question.prompt.contains("fill in the blank", ignoreCase = true))
            assertFalse(question.prompt.contains("______"))
            assertTrue(question.explanation.contains("Physics basics"))
        }
    }

    @Test
    fun sameInputProducesTheSameQuestions() {
        val first = ChoiceQuizBuilder.build(listOf(physics), 8)
        val second = ChoiceQuizBuilder.build(listOf(physics), 8)
        assertEquals(first.map { it.prompt }, second.map { it.prompt })
        assertEquals(first.map { it.options }, second.map { it.options })
        assertEquals(first.map { it.correctIndex }, second.map { it.correctIndex })
    }

    @Test
    fun usesBothDefinitionAndTermShapes() {
        val questions = ChoiceQuizBuilder.build(listOf(physics), 12)
        assertTrue(questions.any { it.prompt.startsWith("Which option best defines") })
        assertTrue(questions.any { it.prompt.startsWith("Which term does this description match?") })
    }

    @Test
    fun capsAtRequestedCount() {
        val questions = ChoiceQuizBuilder.build(listOf(physics), 3)
        assertEquals(3, questions.size)
    }

    @Test
    fun refusesWhenThereAreNotEnoughDistinctFacts() {
        val tiny = source(
            "Tiny note",
            """
                Gravity is a force that pulls two masses toward each other.
                Friction is a force that opposes motion between two touching surfaces.
                Energy is the capacity of a system to do work or transfer heat.
            """.trimIndent()
        )
        assertTrue(ChoiceQuizBuilder.build(listOf(tiny), 20).isEmpty())
    }

    @Test
    fun drawsFromSeveralNotesWithoutRepeatingTheSameQuestion() {
        val chemistry = source(
            "Chemistry basics",
            """
                An atom is the smallest unit of an element that keeps its chemical properties.
                A molecule is a group of atoms joined together by chemical bonds.
                A catalyst is a substance that speeds up a reaction without being used up.
                An ion is an atom or molecule that has gained or lost an electron.
            """.trimIndent()
        )
        val questions = ChoiceQuizBuilder.build(listOf(physics, chemistry), 20)
        assertTrue(questions.size >= 10)
        assertEquals(questions.size, questions.map { it.prompt }.distinct().size)
        assertTrue(questions.any { it.sourceTitle == "Physics basics" })
        assertTrue(questions.any { it.sourceTitle == "Chemistry basics" })
    }

    @Test
    fun distractorsComeFromTheSameNoteBeforeOtherSubjects() {
        val chemistry = source(
            "Chemistry basics",
            """
                An atom is the smallest unit of an element that keeps its chemical properties.
                A molecule is a group of atoms joined together by chemical bonds.
                A catalyst is a substance that speeds up a reaction without being used up.
                An ion is an atom or molecule that has gained or lost an electron.
            """.trimIndent()
        )
        val questions = ChoiceQuizBuilder.build(listOf(physics, chemistry), 20)
        val physicsQuestions = questions.filter { it.sourceTitle == "Physics basics" }
        assertTrue(physicsQuestions.isNotEmpty())
        // The physics note has six definitions, so every distractor should be physics too.
        physicsQuestions.forEach { question ->
            assertFalse(question.options.any { it.contains("atom", ignoreCase = true) })
            assertFalse(question.options.any { it.contains("molecule", ignoreCase = true) })
            assertFalse(question.options.any { it.contains("catalyst", ignoreCase = true) })
        }
    }
}
