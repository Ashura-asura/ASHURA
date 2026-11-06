package com.ashura.tutor.domain

import com.ashura.tutor.domain.runtime.GenerationLimits
import com.ashura.tutor.domain.runtime.ModelRuntime
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class NoModel : ModelRuntime {
    override val isAvailable = false
    override suspend fun generate(request: TutorRequest, limits: GenerationLimits): TutorResponse =
        error("Model should not be invoked")
    override fun unload() = Unit
}

class TaskControllerTest {

    @Test fun arithmeticRoutesToCalculator() = runTest {
        val controller = TaskController(NoModel(), mapOf("calculator" to CalculatorTool()))
        val plan = controller.route("19 + 23")
        assertEquals(listOf("calculator"), plan.tools)
        assertEquals("explain_tool_result", plan.modelRole)
        assertEquals(1, plan.maxToolCalls)
    }

    @Test fun nonArithmeticFallsBackOfflineWhenModelUnavailable() = runTest {
        val controller = TaskController(NoModel(), mapOf("calculator" to CalculatorTool()))
        val plan = controller.route("Explain photosynthesis")
        assertEquals(emptyList(), plan.tools)
        assertEquals("offline_fallback", plan.modelRole)
    }

    @Test fun calculatorExecutesDeterministically() = runTest {
        val controller = TaskController(NoModel(), mapOf("calculator" to CalculatorTool()))
        val plan = controller.route("19 + 23")
        val result = controller.execute(plan, TutorRequest("19 + 23"))
        assertEquals(ResponseMode.DETERMINISTIC, result.mode)
        assertTrue(result.answer.contains("42"))
    }

    @Test fun divisionByZeroIsReported() = runTest {
        val controller = TaskController(NoModel(), mapOf("calculator" to CalculatorTool()))
        val plan = controller.route("8 / 0")
        val result = controller.execute(plan, TutorRequest("8 / 0"))
        assertEquals(ResponseMode.DETERMINISTIC, result.mode)
        assertTrue(result.answer.contains("undefined"))
    }
}
