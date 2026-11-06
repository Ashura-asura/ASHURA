package com.ashura.tutor.domain

import com.ashura.tutor.domain.runtime.GenerationLimits
import com.ashura.tutor.domain.runtime.ModelRuntime
import kotlinx.coroutines.delay
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TutorEngineTest {
    private class NoModel : ModelRuntime {
        override val isAvailable = false
        override suspend fun generate(request: TutorRequest, limits: GenerationLimits): TutorResponse =
            error("Model should not be invoked")
        override fun unload() = Unit
    }

    private val controller = TaskController(NoModel(), mapOf("calculator" to CalculatorTool()))

    @Test fun additionUsesDeterministicPath() = runTest {
        val result = TutorEngine(NoModel(), controller).answer(TutorRequest("19 + 23"))
        assertEquals(ResponseMode.DETERMINISTIC, result.mode)
        assertTrue(result.answer.contains("42"))
    }

    @Test fun divisionByZeroIsExplained() = runTest {
        val result = TutorEngine(NoModel(), controller).answer(TutorRequest("8 / 0"))
        assertTrue(result.answer.contains("undefined"))
    }

    @Test fun noModelDoesNotPretendToKnowTheAnswer() = runTest {
        val result = TutorEngine(NoModel(), controller).answer(TutorRequest("Explain photosynthesis"))
        assertEquals(ResponseMode.OFFLINE_FALLBACK, result.mode)
        assertTrue(result.limitation?.contains("study scaffold") == true)
    }

    @Test(expected = IllegalArgumentException::class)
    fun blankQuestionIsRejected() = runTest {
        TutorEngine(NoModel(), controller).answer(TutorRequest("  "))
    }

    @Test fun toolExecutionHonorsRequestTimeout() = runTest {
        val slowTool = object : TaskController.Tool {
            override val name = "slow"
            override val handles: (String) -> Boolean = { true }
            override suspend fun execute(request: TutorRequest): TaskController.ToolResult {
                delay(2_000)
                return TaskController.ToolResult.Handled("done", ResponseMode.DETERMINISTIC)
            }
        }
        val slowController = TaskController(NoModel(), mapOf("slow" to slowTool))
        val engine = TutorEngine(
            NoModel(), slowController,
            GenerationLimits(timeoutMillis = 1_000)
        )
        try {
            engine.answer(TutorRequest("wait"))
            throw AssertionError("expected request timeout")
        } catch (_: TimeoutCancellationException) {
            // Expected: the request budget cancels the tool coroutine.
        }
    }
}
