package com.ashura.tutor.domain

import com.ashura.tutor.domain.runtime.GenerationLimits
import com.ashura.tutor.domain.runtime.ModelRuntime
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CalculatorToolTest {

    private class NoModel : ModelRuntime {
        override val isAvailable = false
        override suspend fun generate(request: TutorRequest, limits: GenerationLimits): TutorResponse =
            error("should not be invoked")
        override fun unload() = Unit
    }

    private fun controller() = TaskController(NoModel(), mapOf("calculator" to CalculatorTool()))

    @Test fun addition() = runTest {
        val c = controller()
        val plan = c.route("19 + 23")
        val result = c.execute(plan, TutorRequest("19 + 23"))
        assertEquals(ResponseMode.DETERMINISTIC, result.mode)
        assertTrue(result.answer.contains("42"))
    }

    @Test fun subtraction() = runTest {
        val c = controller()
        val plan = c.route("10 - 4")
        val result = c.execute(plan, TutorRequest("10 - 4"))
        assertEquals(ResponseMode.DETERMINISTIC, result.mode)
        assertTrue(result.answer.contains("6"))
    }

    @Test fun multiplication() = runTest {
        val c = controller()
        val plan = c.route("3 * 4")
        val result = c.execute(plan, TutorRequest("3 * 4"))
        assertEquals(ResponseMode.DETERMINISTIC, result.mode)
        assertTrue(result.answer.contains("12"))
    }

    @Test fun division() = runTest {
        val c = controller()
        val plan = c.route("20 / 4")
        val result = c.execute(plan, TutorRequest("20 / 4"))
        assertEquals(ResponseMode.DETERMINISTIC, result.mode)
        assertTrue(result.answer.contains("5"))
    }

    @Test fun power() = runTest {
        val c = controller()
        val plan = c.route("2 ^ 3")
        val result = c.execute(plan, TutorRequest("2 ^ 3"))
        assertEquals(ResponseMode.DETERMINISTIC, result.mode)
        assertTrue(result.answer.contains("8"))
    }

    @Test fun divisionByZero() = runTest {
        val c = controller()
        val plan = c.route("8 / 0")
        val result = c.execute(plan, TutorRequest("8 / 0"))
        assertEquals(ResponseMode.DETERMINISTIC, result.mode)
        assertTrue(result.answer.contains("undefined"))
    }
}

class CalculatorToolRoutingTest {
    @Test fun recognisesExpressionsAndConversionsButNotProse() {
        val tool = CalculatorTool()
        assertTrue(tool.handles("3 + 4 * 2"))
        assertTrue(tool.handles("what is (3+4)*2?"))
        assertTrue(tool.handles("sqrt(16) + 1"))
        assertTrue(tool.handles("convert 5 km to m"))
        assertTrue(!tool.handles("5"))
        assertTrue(!tool.handles("Explain photosynthesis"))
        assertTrue(!tool.handles("what is 2 apples"))
        assertTrue(!tool.handles("1999"))
    }
}
