package com.ashura.tutor.domain

import com.ashura.tutor.domain.runtime.GenerationLimits
import com.ashura.tutor.domain.runtime.ModelRuntime
import com.ashura.tutor.domain.runtime.TutorStreamEvent
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Streaming contract (spec §25 step 4): deterministic tools emit exactly one final event, a working
 * model emits deltas in order followed by one Complete, and a model failure degrades to the offline
 * scaffold rather than leaving the UI hanging.
 */
class StreamingTest {

    private class StreamingRuntime(
        private val chunks: List<String>,
        private val failAfter: Int = Int.MAX_VALUE
    ) : ModelRuntime {
        var generatedRequests = 0
            private set

        override val isAvailable = true

        override suspend fun generate(request: TutorRequest, limits: GenerationLimits): TutorResponse {
            generatedRequests++
            return TutorResponse(chunks.joinToString(""), ResponseMode.LOCAL_MODEL)
        }

        override fun generateStream(request: TutorRequest, limits: GenerationLimits): Flow<TutorStreamEvent> = flow {
            chunks.forEachIndexed { index, chunk ->
                if (index >= failAfter) error("native decode failed")
                emit(TutorStreamEvent.Delta(chunk))
            }
            emit(TutorStreamEvent.Complete(TutorResponse(chunks.joinToString(""), ResponseMode.LOCAL_MODEL)))
        }

        override fun unload() = Unit
    }

    private class OfflineRuntime : ModelRuntime {
        override val isAvailable = false
        override suspend fun generate(request: TutorRequest, limits: GenerationLimits): TutorResponse =
            error("Model should not be invoked")
        override fun unload() = Unit
    }

    private fun controller(runtime: ModelRuntime) =
        TaskController(runtime, mapOf("calculator" to CalculatorTool()))

    @Test fun deterministicToolEmitsOneFinalEventAndNoDeltas() = runTest {
        val events = controller(OfflineRuntime())
            .executeStream(
                TaskController.Plan(tools = listOf("calculator")),
                TutorRequest("19 + 23")
            )
            .toList()

        assertEquals(1, events.size)
        val complete = events.single() as TutorStreamEvent.Complete
        assertEquals(ResponseMode.DETERMINISTIC, complete.response.mode)
        assertTrue(complete.response.answer.contains("42"))
    }

    @Test fun modelStreamEmitsDeltasInOrderThenComplete() = runTest {
        val runtime = StreamingRuntime(listOf("Hello", " ", "world"))
        val events = controller(runtime)
            .executeStream(TaskController.Plan(), TutorRequest("Say hello"))
            .toList()

        val deltas = events.filterIsInstance<TutorStreamEvent.Delta>().map { it.text }
        assertEquals(listOf("Hello", " ", "world"), deltas)
        assertTrue(events.last() is TutorStreamEvent.Complete)

        val complete = events.last() as TutorStreamEvent.Complete
        assertEquals("Hello world", complete.response.answer)
        assertEquals(ResponseMode.LOCAL_MODEL, complete.response.mode)
        assertEquals(0, runtime.generatedRequests) // streaming path only
    }

    @Test fun modelCompleteGainsTheUnverifiedLimitation() = runTest {
        val events = controller(StreamingRuntime(listOf("Answer")))
            .executeStream(TaskController.Plan(), TutorRequest("Why?"))
            .toList()

        val complete = events.last() as TutorStreamEvent.Complete
        assertTrue(complete.response.limitation?.contains("not independently verified") == true)
    }

    @Test fun modelFailureFallsBackToScaffoldAfterDeltas() = runTest {
        val events = controller(StreamingRuntime(listOf("partial", " then boom"), failAfter = 1))
            .executeStream(TaskController.Plan(), TutorRequest("Explain entropy"))
            .toList()

        assertTrue(events.any { it is TutorStreamEvent.Delta })
        val complete = events.last() as TutorStreamEvent.Complete
        assertEquals(ResponseMode.OFFLINE_FALLBACK, complete.response.mode)
        assertTrue(complete.response.answer.contains("STEPS:"))
        assertTrue(complete.response.limitation?.contains("study scaffold") == true)
    }

    @Test fun offlineRuntimeEmitsScaffoldWithoutCallingTheModel() = runTest {
        val events = controller(OfflineRuntime())
            .executeStream(TaskController.Plan(), TutorRequest("Explain gravity"))
            .toList()

        val complete = events.single() as TutorStreamEvent.Complete
        assertEquals(ResponseMode.OFFLINE_FALLBACK, complete.response.mode)
        assertTrue(complete.response.answer.contains("ANSWER:"))
    }

    @Test fun socraticOfflineScaffoldAsksInsteadOfAnswering() = runTest {
        val events = controller(OfflineRuntime())
            .executeStream(
                TaskController.Plan(),
                TutorRequest("What is a derivative?", style = TutorStyle.SOCRATIC)
            )
            .toList()

        val text = (events.single() as TutorStreamEvent.Complete).response.answer
        assertTrue(text.contains("What do you already know"))
        assertTrue(!text.contains("Let's work through this carefully."))
    }

    @Test fun engineStreamRoutesThroughTheController() = runTest {
        val engine = TutorEngine(OfflineRuntime(), controller(OfflineRuntime()))
        val events = engine.answerStream(TutorRequest("19 + 23")).toList()

        val complete = events.single() as TutorStreamEvent.Complete
        assertEquals(ResponseMode.DETERMINISTIC, complete.response.mode)
    }

    @Test(expected = IllegalArgumentException::class)
    fun engineStreamRejectsBlankQuestions() = runTest {
        TutorEngine(OfflineRuntime(), controller(OfflineRuntime()))
            .answerStream(TutorRequest("   "))
            .toList()
    }
}
