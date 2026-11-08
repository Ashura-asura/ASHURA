package com.ashura.tutor.domain

import com.ashura.tutor.domain.assessment.ChoiceQuestion
import com.ashura.tutor.domain.assessment.TestMode
import com.ashura.tutor.domain.assessment.TestSession
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TestSessionTest {

    private fun question(index: Int, correct: Int = 0) = ChoiceQuestion(
        id = "q$index",
        prompt = "Question $index",
        options = listOf("A$index", "B$index", "C$index", "D$index"),
        correctIndex = correct,
        explanation = "Because $index",
        sourceTitle = "Note",
        chunkOrdinal = index
    )

    private fun session(count: Int = 4, duration: Int = 60) = TestSession(
        mode = TestMode.QUICK,
        title = "All your notes",
        questions = List(count) { question(it, it % 4) },
        answers = List(count) { null },
        currentIndex = 0,
        startedAtMillis = 1_000L,
        durationSeconds = duration
    )

    @Test
    fun countdownUsesWholeSecondsAndNeverGoesNegative() {
        val s = session(duration = 60)
        assertEquals(60, s.remainingSeconds(1_000L))
        assertEquals(30, s.remainingSeconds(31_000L))
        assertEquals(0, s.remainingSeconds(61_000L))
        assertEquals(0, s.remainingSeconds(90_000L))
    }

    @Test
    fun selectingAndNavigatingKeepsEachAnswer() {
        var s = session()
        s = s.select(2)
        s = s.next()
        s = s.select(3)
        s = s.previous()
        assertEquals(2, s.answerAt(0))
        assertEquals(3, s.answerAt(1))
        assertEquals(2, s.answeredCount)
        assertEquals(0, s.currentIndex)
    }

    @Test
    fun ignoresInvalidOptionAndOutOfRangeNavigation() {
        val s = session().select(9).goTo(99)
        assertEquals(0, s.currentIndex)
        assertEquals(null, s.answerAt(0))
        assertEquals(0, s.previous().currentIndex)
        assertEquals(1, s.next().currentIndex)
    }

    @Test
    fun marksOnlyTheCorrectChoices() {
        var s = session()
        s = s.select(0)          // correct (question 0 has correct 0)
        s = s.next().select(0)   // wrong (question 1 has correct 1)
        s = s.next().select(2)   // correct
        s = s.next().select(3)   // correct
        s = s.finish(61_000L)
        assertEquals(3, s.correctCount)
        assertEquals(0, s.unansweredCount)
        assertEquals(75, s.scorePercent)
    }

    @Test
    fun finishingFreezesAnswersAndRecordsTime() {
        var s = session(duration = 120).select(0).finish(46_000L)
        assertTrue(s.isFinished)
        assertEquals(45, s.timeTakenSeconds)
        assertEquals(0, s.remainingSeconds(50_000L))
        s = s.select(1)
        assertEquals(0, s.answerAt(0))
        val again = s.finish(99_000L)
        assertEquals(46_000L, again.finishedAtMillis)
    }

    @Test
    fun unansweredQuestionsCountAsWrong() {
        val s = session(count = 3).finish(5_000L)
        assertEquals(0, s.correctCount)
        assertEquals(3, s.unansweredCount)
        assertEquals(0, s.scorePercent)
        assertFalse(s.timedOut)
    }

    @Test
    fun timeoutIsRecorded() {
        val s = session().finish(61_000L, timedOut = true)
        assertTrue(s.timedOut)
        assertEquals(0, s.correctCount)
    }

    @Test
    fun percentageRoundsToNearestWholeNumber() {
        assertEquals(67, TestSession.percent(2, 3))
        assertEquals(33, TestSession.percent(1, 3))
        assertEquals(0, TestSession.percent(0, 0))
        assertEquals(100, TestSession.percent(5, 5))
    }
}
