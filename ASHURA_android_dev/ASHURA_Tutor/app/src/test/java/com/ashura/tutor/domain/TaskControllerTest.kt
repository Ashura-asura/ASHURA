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

private class RecordingModel : ModelRuntime {
    override val isAvailable = true
    var received: TutorRequest? = null
    override suspend fun generate(request: TutorRequest, limits: GenerationLimits): TutorResponse {
        received = request
        return TutorResponse("generated answer", ResponseMode.LOCAL_MODEL)
    }
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
        assertEquals(emptyList<String>(), plan.tools)
        assertEquals("offline_fallback", plan.modelRole)
        val response = controller.execute(plan, TutorRequest("Explain photosynthesis"))
        assertEquals(ResponseMode.OFFLINE_FALLBACK, response.mode)
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

    @Test fun availableRuntimeIsActuallyInvokedAndContextIsBounded() = runTest {
        val runtime = RecordingModel()
        val limits = GenerationLimits(maxContextCharacters = 1_000)
        val controller = TaskController(runtime, emptyMap(), limits)
        val request = TutorRequest(
            question = "Explain photosynthesis",
            retrievedContext = listOf(
                ContextSnippet("old", "A".repeat(700), "test"),
                ContextSnippet("new", "B".repeat(700), "test")
            )
        )
        val response = controller.execute(controller.route(request.question), request)
        assertEquals(ResponseMode.LOCAL_MODEL, response.mode)
        assertEquals("generated answer", response.answer)
        val received = requireNotNull(runtime.received)
        assertTrue(received.retrievedContext.sumOf { it.text.length } <= 1_000 - request.question.length)
        assertEquals("new", received.retrievedContext.last().title)
    }
}
