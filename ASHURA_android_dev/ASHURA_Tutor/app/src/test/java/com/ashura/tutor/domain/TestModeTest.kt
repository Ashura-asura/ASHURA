package com.ashura.tutor.domain

import com.ashura.tutor.domain.assessment.TestMode
import com.ashura.tutor.domain.assessment.formatClock
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class TestModeTest {

    @Test
    fun modesHaveTheRequestedQuestionCountsAndAutoTimers() {
        assertEquals(20, TestMode.QUICK.questionCount)
        assertEquals(35, TestMode.MEDIUM.questionCount)
        assertEquals(50, TestMode.LONG.questionCount)
        assertEquals(20 * 60, TestMode.QUICK.durationSeconds)
        assertEquals(35 * 60, TestMode.MEDIUM.durationSeconds)
        assertEquals(50 * 60, TestMode.LONG.durationSeconds)
    }

    @Test
    fun parsesStoredModeNamesCaseInsensitively() {
        assertEquals(TestMode.QUICK, TestMode.of("quick"))
        assertEquals(TestMode.MEDIUM, TestMode.of("MEDIUM"))
        assertEquals(TestMode.LONG, TestMode.of("Long"))
        assertNull(TestMode.of(null))
        assertNull(TestMode.of("unknown"))
    }

    @Test
    fun formatsClockWithoutNegativeValues() {
        assertEquals("0:00", formatClock(0))
        assertEquals("1:05", formatClock(65))
        assertEquals("50:00", formatClock(3_000))
        assertEquals("0:00", formatClock(-5))
    }
}
