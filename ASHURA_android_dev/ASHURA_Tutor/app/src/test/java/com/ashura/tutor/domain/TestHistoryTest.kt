package com.ashura.tutor.domain

import com.ashura.tutor.domain.assessment.TestHistory
import com.ashura.tutor.domain.assessment.TestResultSummary
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class TestHistoryTest {

    private fun result(
        id: String,
        mode: String,
        correct: Int,
        total: Int,
        finishedAt: Long
    ) = TestResultSummary(
        id = id,
        mode = mode,
        title = "All your notes",
        correct = correct,
        total = total,
        timeTakenSeconds = 300,
        timedOut = false,
        finishedAt = finishedAt
    )

    @Test
    fun comparesEachModeWithItsPreviousResult() {
        val newestQuick = result("q2", "QUICK", 15, 20, 300)
        val medium = result("m1", "MEDIUM", 30, 35, 250)
        val olderQuick = result("q1", "QUICK", 10, 20, 200)

        val changes = TestHistory.withChanges(listOf(newestQuick, medium, olderQuick))

        assertEquals(3, changes.size)
        assertEquals(5, changes[0].marksDelta)
        assertEquals(25, changes[0].percentDelta)
        assertNull(changes[1].marksDelta) // first Medium test
        assertNull(changes[2].marksDelta) // previous Quick in this list
        assertEquals("q1", changes[0].previous?.id)
    }

    @Test
    fun reportsNegativeAndZeroChanges() {
        val newest = result("q3", "QUICK", 8, 20, 400)
        val previous = result("q2", "QUICK", 12, 20, 300)
        val oldest = result("q1", "QUICK", 12, 20, 200)
        val changes = TestHistory.withChanges(listOf(newest, previous, oldest))
        assertEquals(-4, changes[0].marksDelta)
        assertEquals(-20, changes[0].percentDelta)
        assertEquals(0, changes[1].marksDelta)
        assertEquals(0, changes[1].percentDelta)
    }
}
